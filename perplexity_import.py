import json
import logging
import os
import re
import sys
from urllib import request as urlrequest

from sqlalchemy import text
from dotenv import load_dotenv
try:
    import certifi
except ImportError:
    certifi = None
import ssl

from db import engine
from criteria_utils import normalize_criteria_type, normalize_criteria_key, validate_criteria_key

ALLOWED_ORG_TYPES = {
    'Government',
    'University',
    'Private',
    'Foundation',
    'Nonprofit'
}

ALLOWED_STATUSES = {
    'active',
    'expired',
    'draft',
    'suspended',
    'inactive'
}


def normalize_org_type(value):
    if not value:
        return 'Private'
    raw = str(value).strip().lower()
    mapping = {
        'government': 'Government',
        'govt': 'Government',
        'university': 'University',
        'college': 'University',
        'private': 'Private',
        'company': 'Private',
        'corporate': 'Private',
        'foundation': 'Foundation',
        'nonprofit': 'Nonprofit',
        'non-profit': 'Nonprofit',
        'ngo': 'Nonprofit'
    }
    mapped = mapping.get(raw)
    if mapped in ALLOWED_ORG_TYPES:
        return mapped
    return 'Private'


def is_valid_date(value):
    if not value:
        return False
    return re.match(r'^\d{4}-\d{2}-\d{2}$', str(value)) is not None

def load_prompt(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return handle.read().strip()


def extract_json(content):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    raise ValueError('Response did not contain valid JSON.')


def call_perplexity(prompt):
    api_key = os.getenv('PERPLEXITY_API_KEY')
    api_url = os.getenv('PERPLEXITY_API_URL', 'https://api.perplexity.ai/chat/completions')
    model = os.getenv('PERPLEXITY_MODEL', 'sonar')

    if not api_key:
        raise RuntimeError('PERPLEXITY_API_KEY is missing. Set it in .env.')

    payload = json.dumps({
        'model': model,
        'messages': [
            {
                'role': 'system',
                'content': 'You are a data extraction assistant. Output JSON only.'
            },
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }).encode('utf-8')

    req = urlrequest.Request(
        api_url,
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    )

    ssl_context = None
    if certifi:
        ssl_context = ssl.create_default_context(cafile=certifi.where())

    timeout_seconds = int(os.getenv('PERPLEXITY_TIMEOUT_SECONDS', '30'))
    with urlrequest.urlopen(req, context=ssl_context, timeout=timeout_seconds) as resp:
        raw = resp.read().decode('utf-8')
        data = json.loads(raw)
        content = data['choices'][0]['message']['content']
        return extract_json(content), content


def find_or_create_organization(conn, org):
    name = org.get('name')
    org_type = normalize_org_type(org.get('type'))
    website = org.get('website')
    jurisdiction_state = org.get('jurisdiction_state') or org.get('offered_location')
    jurisdiction_country = org.get('jurisdiction_country')

    if not name or not org_type:
        raise ValueError('Organization name and type are required.')

    select_org = text('''
        SELECT id FROM organizations
        WHERE name = :name AND type = :type
        LIMIT 1
    ''')
    result = conn.execute(select_org, {'name': name, 'type': org_type}).first()
    if result:
        return result.id

    insert_org = text('''
        INSERT INTO organizations (name, type, website, jurisdiction_state, jurisdiction_country)
        VALUES (:name, :type, :website, :jurisdiction_state, :jurisdiction_country)
    ''')
    result = conn.execute(
        insert_org,
        {
            'name': name,
            'type': org_type,
            'website': website,
            'jurisdiction_state': jurisdiction_state,
            'jurisdiction_country': jurisdiction_country
        }
    )
    return result.lastrowid


def insert_scholarship(conn, scholarship, organization_id):
    status = str(scholarship.get('status', 'active')).strip().lower()
    if status not in ALLOWED_STATUSES:
        status = 'active'
    select_existing = text('''
        SELECT id FROM scholarships
        WHERE title = :title AND organization_id = :organization_id AND deadline = :deadline
        LIMIT 1
    ''')
    existing = conn.execute(select_existing, {
        'title': scholarship['title'].strip(),
        'organization_id': organization_id,
        'deadline': scholarship['deadline']
    }).first()
    if existing:
        return None

    eligibility_raw_text = scholarship.get('eligibility_raw_text')
    if not eligibility_raw_text and scholarship.get('eligibility_criteria'):
        eligibility_raw_text = json.dumps(
            scholarship.get('eligibility_criteria', []),
            ensure_ascii=True
        )
    insert_sql = text('''
        INSERT INTO scholarships
        (title, description, amount, deadline, organization_id, application_url, status, industry, eligibility_raw_text, created_at)
        VALUES
        (:title, :description, :amount, :deadline, :organization_id, :application_url, :status, :industry, :eligibility_raw_text, NOW())
    ''')
    jurisdiction_state = scholarship.get('jurisdiction_state') or scholarship.get('offered_location')
    if jurisdiction_state:
        update_org = text('''
            UPDATE organizations
            SET jurisdiction_state = :jurisdiction_state
            WHERE id = :organization_id
            AND (jurisdiction_state IS NULL OR jurisdiction_state = '')
        ''')
        conn.execute(update_org, {
            'jurisdiction_state': jurisdiction_state,
            'organization_id': organization_id
        })
    jurisdiction_country = scholarship.get('jurisdiction_country')
    if jurisdiction_country:
        update_org = text('''
            UPDATE organizations
            SET jurisdiction_country = :jurisdiction_country
            WHERE id = :organization_id
            AND (jurisdiction_country IS NULL OR jurisdiction_country = '')
        ''')
        conn.execute(update_org, {
            'jurisdiction_country': jurisdiction_country,
            'organization_id': organization_id
        })
    result = conn.execute(insert_sql, {
        'title': scholarship['title'].strip(),
        'description': scholarship['description'].strip(),
        'amount': float(scholarship['amount']),
        'deadline': scholarship['deadline'],
        'organization_id': organization_id,
        'application_url': scholarship.get('application_url'),
        'status': status,
        'industry': scholarship.get('industry'),
        'eligibility_raw_text': eligibility_raw_text
    })
    return result.lastrowid


def insert_criteria(conn, scholarship_id, criteria, source_url=None):
    criteria_type = normalize_criteria_type(
        criteria.get('criteria_type'),
        scholarship_id=scholarship_id,
        source_url=source_url,
        criteria=criteria
    )
    criteria_key = normalize_criteria_key(criteria.get('criteria_key'))
    if not criteria_key and criteria_type in {'location', 'demographic'}:
        raise ValueError('Eligibility criteria must include criteria_key')
    if not criteria_key:
        criteria_key = normalize_criteria_key(criteria_type)
    if not validate_criteria_key(criteria_type, criteria_key):
        raise ValueError(f'Invalid criteria_key for {criteria_type}')
    insert_sql = text('''
        INSERT INTO eligibility_criteria
        (scholarship_id, criteria_type, criteria_key, required_value, is_required)
        VALUES
        (:scholarship_id, :criteria_type, :criteria_key, :required_value, :is_required)
    ''')
    conn.execute(insert_sql, {
        'scholarship_id': scholarship_id,
        'criteria_type': criteria_type,
        'criteria_key': criteria_key,
        'required_value': criteria['required_value'],
        'is_required': bool(criteria.get('is_required', True))
    })
    return True


def validate_scholarship(scholarship):
    required_fields = ['title', 'description', 'amount', 'deadline', 'organization']
    for field in required_fields:
        if not scholarship.get(field):
            return False

    organization = scholarship['organization']
    if not organization.get('name') or not organization.get('type'):
        return False

    if not is_valid_date(scholarship.get('deadline')):
        return False

    return True


def main():
    load_dotenv()
    prompt_path = os.getenv('PERPLEXITY_PROMPT_FILE', 'perplexity_prompt.txt')
    base_prompt = load_prompt(prompt_path)

    batch_size = int(os.getenv('PERPLEXITY_BATCH_SIZE', '10'))
    batch_total = int(os.getenv('PERPLEXITY_BATCHES', '5'))
    timeout_seconds = os.getenv('PERPLEXITY_TIMEOUT_SECONDS')
    if not timeout_seconds:
        os.environ['PERPLEXITY_TIMEOUT_SECONDS'] = '60'

    inserted = 0
    skipped = 0
    skipped_invalid = 0

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for batch_index in range(1, batch_total + 1):
                prompt = (
                    f"{base_prompt}\n"
                    f"Batch {batch_index} of {batch_total}. "
                    f"Return exactly {batch_size} scholarships. "
                    f"Avoid duplicates from previous batches."
                )

                response, raw_content = call_perplexity(prompt)
                scholarships = response.get('scholarships', [])
                if not scholarships:
                    debug_path = os.getenv('PERPLEXITY_LAST_RESPONSE_FILE', 'perplexity_last_response.txt')
                    with open(debug_path, 'w', encoding='utf-8') as handle:
                        handle.write(raw_content)
                    print(f'No scholarships found in response. Saved raw response to {debug_path}.')
                    trans.rollback()
                    return 1

                for scholarship in scholarships:
                    if not validate_scholarship(scholarship):
                        skipped_invalid += 1
                        continue
                    org_id = find_or_create_organization(conn, scholarship['organization'])
                    scholarship_id = insert_scholarship(conn, scholarship, org_id)
                    if scholarship_id is None:
                        skipped += 1
                        continue
                    criteria_list = scholarship.get('eligibility_criteria', [])
                    if criteria_list:
                        for criteria in criteria_list:
                            try:
                                insert_criteria(
                                    conn,
                                    scholarship_id,
                                    criteria,
                                    source_url=scholarship.get('application_url')
                                )
                            except Exception as exc:
                                logging.exception(
                                    "Failed to insert eligibility criteria: scholarship_id=%s criteria=%s error=%s",
                                    scholarship_id,
                                    criteria,
                                    exc
                                )
                    else:
                        try:
                            insert_criteria(conn, scholarship_id, {
                                'criteria_type': 'other',
                                'criteria_key': 'raw_text',
                                'required_value': 'Eligibility pending',
                                'is_required': True
                            })
                        except Exception as exc:
                            logging.exception(
                                "Failed to insert fallback eligibility criteria: scholarship_id=%s error=%s",
                                scholarship_id,
                                exc
                            )
                    inserted += 1

            trans.commit()
        except Exception:
            trans.rollback()
            raise

    print(
        f'Inserted {inserted} scholarships. '
        f'Skipped {skipped} duplicates. '
        f'Skipped {skipped_invalid} invalid.'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
