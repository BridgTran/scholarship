import argparse
import json
import sys

from dotenv import load_dotenv

from db import engine
from perplexity_import import (
    call_perplexity,
    find_or_create_organization,
    insert_criteria,
    insert_scholarship,
    is_valid_date,
)


def build_prompt(query, count):
    return (
        "Return JSON only (no markdown). Use this schema:\n"
        "{\n"
        "  \"scholarships\": [\n"
        "    {\n"
        "      \"title\": \"...\",\n"
        "      \"description\": \"...\",\n"
        "      \"amount\": 5000.0,\n"
        "      \"deadline\": \"YYYY-MM-DD\",\n"
        "      \"application_url\": \"https://...\",\n"
        "      \"jurisdiction_state\": \"NSW\",\n"
        "      \"jurisdiction_country\": \"Australia\",\n"
        "      \"industry\": \"stem|health|business|arts|education|law|trades|agriculture|other\",\n"
        "      \"status\": \"active\",\n"
        "      \"organization\": {\n"
        "        \"name\": \"...\",\n"
        "        \"type\": \"Government|University|Private|Foundation|Nonprofit\",\n"
        "        \"website\": \"https://...\"\n"
        "      },\n"
        "      \"eligibility_criteria\": [],\n"
        "      \"eligibility_raw_text\": \"...\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Only include scholarships with a valid deadline in YYYY-MM-DD format.\n"
        "If a field is not available (except deadline), set it to null.\n"
        f"Query: {query}\n"
        f"Return up to {count} scholarships."
    )


def coerce_scholarship(raw):
    title = (raw.get('title') or '').strip()
    if not title:
        return None
    org = raw.get('organization') or {}
    if not org.get('name') or not org.get('type'):
        return None
    amount = raw.get('amount')
    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        amount_value = 0.0
    deadline = raw.get('deadline')
    deadline_value = deadline if is_valid_date(deadline) else None
    if deadline_value is None:
        return None
    return {
        'title': title,
        'description': (raw.get('description') or '').strip(),
        'amount': amount_value,
        'deadline': deadline_value,
        'application_url': raw.get('application_url'),
        'status': raw.get('status') or 'active',
        'industry': raw.get('industry'),
        'jurisdiction_state': raw.get('jurisdiction_state'),
        'jurisdiction_country': raw.get('jurisdiction_country'),
        'organization': org,
        'eligibility_criteria': raw.get('eligibility_criteria') or [],
        'eligibility_raw_text': raw.get('eligibility_raw_text')
    }


def insert_scraped(scraped):
    inserted = 0
    skipped = 0
    skipped_invalid = 0
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for scholarship in scraped:
                normalized = coerce_scholarship(scholarship)
                if not normalized:
                    skipped_invalid += 1
                    continue
                org_id = find_or_create_organization(conn, normalized['organization'])
                scholarship_id = insert_scholarship(conn, normalized, org_id)
                if scholarship_id is None:
                    skipped += 1
                    continue
                criteria_list = normalized.get('eligibility_criteria', [])
                if criteria_list:
                    for criteria in criteria_list:
                        insert_criteria(
                            conn,
                            scholarship_id,
                            criteria,
                            source_url=normalized.get('application_url')
                        )
                inserted += 1
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    return inserted, skipped, skipped_invalid


def main():
    load_dotenv(dotenv_path='.env')
    parser = argparse.ArgumentParser(description='Scrape scholarships via Perplexity query.')
    parser.add_argument('--query', required=True, help='Search query for Perplexity.')
    parser.add_argument('--count', type=int, default=20, help='Number of scholarships to return.')
    parser.add_argument('--prompt', default='perplexity_prompt.txt', help='Prompt file path.')
    parser.add_argument('--output', default='scraped_scholarships.json', help='Output JSON path.')
    parser.add_argument('--insert', action='store_true', help='Insert results into DB.')
    args = parser.parse_args()

    prompt = build_prompt(args.query, args.count)
    response, raw_content = call_perplexity(prompt)
    scholarships = response.get('scholarships', []) if isinstance(response, dict) else []
    if not scholarships:
        with open('perplexity_last_response.txt', 'w', encoding='utf-8') as handle:
            handle.write(raw_content)

    with open(args.output, 'w', encoding='utf-8') as handle:
        json.dump({'scholarships': scholarships}, handle, ensure_ascii=True, indent=2)
    print(f"Saved {len(scholarships)} scholarships to {args.output}")

    if args.insert:
        inserted, skipped, skipped_invalid = insert_scraped(scholarships)
        print(
            f'Inserted {inserted} scholarships. '
            f'Skipped {skipped} duplicates. '
            f'Skipped {skipped_invalid} invalid.'
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
