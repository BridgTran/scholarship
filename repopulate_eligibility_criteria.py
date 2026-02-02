import argparse
import json
import re
import logging

from sqlalchemy import text, bindparam

from db import engine
from criteria_utils import (
    normalize_criteria_key,
    normalize_criteria_type,
    validate_criteria_key
)


def parse_raw_criteria(raw_text):
    if not raw_text:
        return []
    raw_text = raw_text.strip()
    if not raw_text:
        return []
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict) and 'eligibility_criteria' in parsed:
        parsed = parsed['eligibility_criteria']
    if isinstance(parsed, list):
        return parsed
    return []


COUNTRY_NAMES = [
    'Australia',
    'Bangladesh',
    'Brazil',
    'Canada',
    'China',
    'France',
    'Germany',
    'Hong Kong',
    'India',
    'Indonesia',
    'Ireland',
    'Italy',
    'Japan',
    'Kenya',
    'Malaysia',
    'Mexico',
    'Nepal',
    'New Zealand',
    'Nigeria',
    'Pakistan',
    'Philippines',
    'Singapore',
    'South Africa',
    'South Korea',
    'Sri Lanka',
    'Thailand',
    'United Kingdom',
    'United States',
    'United States of America',
    'Vietnam'
]

DEMONYMS = {
    'australian': 'Australia',
    'bangladeshi': 'Bangladesh',
    'brazilian': 'Brazil',
    'canadian': 'Canada',
    'chinese': 'China',
    'french': 'France',
    'german': 'Germany',
    'hong konger': 'Hong Kong',
    'indian': 'India',
    'indonesian': 'Indonesia',
    'irish': 'Ireland',
    'italian': 'Italy',
    'japanese': 'Japan',
    'kenyan': 'Kenya',
    'malaysian': 'Malaysia',
    'mexican': 'Mexico',
    'nepali': 'Nepal',
    'new zealander': 'New Zealand',
    'nigerian': 'Nigeria',
    'pakistani': 'Pakistan',
    'filipino': 'Philippines',
    'singaporean': 'Singapore',
    'south african': 'South Africa',
    'south korean': 'South Korea',
    'sri lankan': 'Sri Lanka',
    'thai': 'Thailand',
    'british': 'United Kingdom',
    'uk': 'United Kingdom',
    'american': 'United States',
    'usa': 'United States',
    'us': 'United States',
    'vietnamese': 'Vietnam'
}

COUNTRY_PATTERN = '|'.join(sorted((re.escape(name) for name in COUNTRY_NAMES), key=len, reverse=True))
DEMONYM_PATTERN = '|'.join(sorted((re.escape(name) for name in DEMONYMS.keys()), key=len, reverse=True))

COUNTRY_CONTEXT_PATTERNS = [
    re.compile(rf'\b(?:citizens?|nationals?|residents?)\s+of\s+({COUNTRY_PATTERN})\b', re.IGNORECASE),
    re.compile(rf'\b({COUNTRY_PATTERN})\s+(?:citizens?|nationals?|residents?)\b', re.IGNORECASE),
    re.compile(rf'\bfrom\s+({COUNTRY_PATTERN})\b', re.IGNORECASE),
    re.compile(rf'\bfor\s+({COUNTRY_PATTERN})\s+(?:students|citizens|nationals)\b', re.IGNORECASE),
    re.compile(rf'\b({COUNTRY_PATTERN})\s+students\b', re.IGNORECASE),
    re.compile(rf'\b({COUNTRY_PATTERN})\s+citizens?\b', re.IGNORECASE)
]

DEMONYM_CONTEXT_PATTERN = re.compile(
    rf'\b({DEMONYM_PATTERN})s?\b',
    re.IGNORECASE
)


def extract_from_raw_text(raw_text):
    extracted = []
    if not raw_text:
        return extracted
    text_lower = raw_text.lower()
    upper_text = raw_text.upper()
    for state in ['NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT']:
        if re.search(rf'\b{state}\b', upper_text):
            extracted.append({
                'criteria_type': 'location',
                'criteria_key': 'study_state',
                'required_value': state,
                'is_required': True
            })

    study_country_patterns = [
        r'\bstudy in australia\b',
        r'\bstudying in australia\b',
        r'\benrolled in australia\b',
        r'\bat an australian university\b',
        r'\baustralian year 12\b'
    ]
    for pattern in study_country_patterns:
        if re.search(pattern, text_lower):
            extracted.append({
                'criteria_type': 'location',
                'criteria_key': 'study_country',
                'required_value': 'AU',
                'is_required': True
            })
            break

    if 'international student' in text_lower:
        extracted.append({
            'criteria_type': 'demographic',
            'criteria_key': 'residency_status',
            'required_value': 'INTERNATIONAL',
            'is_required': True
        })
    if 'australian citizen' in text_lower:
        extracted.append({
            'criteria_type': 'demographic',
            'criteria_key': 'residency_status',
            'required_value': 'CITIZEN',
            'is_required': True
        })
    if 'permanent resident' in text_lower:
        extracted.append({
            'criteria_type': 'demographic',
            'criteria_key': 'residency_status',
            'required_value': 'PR',
            'is_required': True
        })
    if re.search(r'\bnot (an )?australian citizen\b', text_lower):
        extracted.append({
            'criteria_type': 'demographic',
            'criteria_key': 'residency_status',
            'required_value': 'INTERNATIONAL',
            'is_required': True
        })
    if re.search(r'\bnot (a )?permanent resident\b', text_lower):
        extracted.append({
            'criteria_type': 'demographic',
            'criteria_key': 'residency_status',
            'required_value': 'INTERNATIONAL',
            'is_required': True
        })
    if 'domestic student' in text_lower:
        extracted.append({
            'criteria_type': 'demographic',
            'criteria_key': 'residency_status',
            'required_value': 'CITIZEN_OR_PR',
            'is_required': True
        })

    if re.search(r'\bfull[-\s]?time\b', text_lower):
        extracted.append({
            'criteria_type': 'other',
            'criteria_key': 'study_load',
            'required_value': 'FULL_TIME',
            'is_required': True
        })
    if re.search(r'\bpart[-\s]?time\b', text_lower):
        extracted.append({
            'criteria_type': 'other',
            'criteria_key': 'study_load',
            'required_value': 'PART_TIME',
            'is_required': True
        })

    if re.search(r'\b(undergraduate|bachelor|ug)\b', text_lower):
        extracted.append({
            'criteria_type': 'academic_level',
            'criteria_key': 'level',
            'required_value': 'UNDERGRADUATE',
            'is_required': True
        })
    if re.search(r'\b(postgraduate|master|pg)\b', text_lower):
        extracted.append({
            'criteria_type': 'academic_level',
            'criteria_key': 'level',
            'required_value': 'POSTGRADUATE',
            'is_required': True
        })
    if re.search(r'\b(ph\.?d|doctor of philosophy|higher degree by research)\b', text_lower):
        extracted.append({
            'criteria_type': 'academic_level',
            'criteria_key': 'level',
            'required_value': 'HDR',
            'is_required': True
        })

    if 'full-fee paying' in text_lower:
        extracted.append({
            'criteria_type': 'other',
            'criteria_key': 'fee_status',
            'required_value': 'FULL_FEE',
            'is_required': True
        })

    for pattern in COUNTRY_CONTEXT_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            country = match.group(1)
            clause_start = max(
                raw_text.rfind('.', 0, match.start()),
                raw_text.rfind(';', 0, match.start()),
                raw_text.rfind('\n', 0, match.start())
            )
            clause_start = 0 if clause_start == -1 else clause_start + 1
            clause = raw_text[clause_start:match.end()].lower()
            if any(term in clause for term in ['not', 'excluding', 'ineligible', 'must not be']):
                break
            if re.search(rf'\b{re.escape(country)}\s+citizens?\b', match.group(0), re.IGNORECASE):
                start_idx = max(0, raw_text.rfind('.', 0, match.start()) + 1)
                sentence = raw_text[start_idx:match.end()]
                if re.search(r'\bnot\b', sentence, re.IGNORECASE):
                    break
            if country.lower() != 'australia':
                extracted.append({
                    'criteria_type': 'demographic',
                    'criteria_key': 'nationality',
                    'required_value': country,
                    'is_required': True
                })
            break
    else:
        demonym_match = DEMONYM_CONTEXT_PATTERN.search(raw_text)
        if demonym_match:
            demonym = demonym_match.group(1).lower()
            country = DEMONYMS.get(demonym)
            if country and country.lower() != 'australia':
                extracted.append({
                    'criteria_type': 'demographic',
                    'criteria_key': 'nationality',
                    'required_value': country,
                    'is_required': True
                })

    return extracted


def coerce_criteria_row(raw_item):
    criteria_type = raw_item.get('criteria_type') or raw_item.get('type')
    required_value = (
        raw_item.get('required_value')
        or raw_item.get('value')
        or raw_item.get('requiredValue')
    )
    criteria_key = raw_item.get('criteria_key') or raw_item.get('key')
    is_required = raw_item.get('is_required')
    return criteria_type, criteria_key, required_value, is_required


def main():
    parser = argparse.ArgumentParser(
        description='Repopulate eligibility_criteria from stored raw text.'
    )
    parser.add_argument(
        '--replace',
        action='store_true',
        help='Delete existing eligibility_criteria rows before inserting.'
    )
    parser.add_argument(
        '--ids',
        help='Comma-separated scholarship IDs to process.'
    )
    args = parser.parse_args()

    with engine.begin() as conn:
        cols = {
            row.COLUMN_NAME
            for row in conn.execute(text(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scholarships'"
            ))
        }
        has_eligible_location = 'eligible_location' in cols
        has_origin_country = 'student_origin_country' in cols
        has_origin_country_alt = 'student_country_of_origin' in cols

        ids = []
        if args.ids:
            ids = [item.strip() for item in args.ids.split(',') if item.strip()]

        if ids:
            stmt = text('''
                SELECT id, eligibility_raw_text
                FROM scholarships
                WHERE id IN :ids
            ''').bindparams(bindparam('ids', expanding=True))
            scholarships = conn.execute(
                stmt,
                {'ids': [int(item) for item in ids]}
            ).fetchall()
        else:
            scholarships = conn.execute(text('''
                SELECT id, eligibility_raw_text
                FROM scholarships
            ''')).fetchall()

        inserted = 0
        skipped = 0

        for row in scholarships:
            existing_count = conn.execute(
                text('''
                    SELECT COUNT(*) AS total
                    FROM eligibility_criteria
                    WHERE scholarship_id = :scholarship_id
                '''),
                {'scholarship_id': row.id}
            ).scalar()
            raw_text = row.eligibility_raw_text or ''
            raw_items = parse_raw_criteria(raw_text)
            raw_items.extend(extract_from_raw_text(raw_text))

            if has_eligible_location:
                eligible_location = conn.execute(
                    text('SELECT eligible_location FROM scholarships WHERE id = :sid'),
                    {'sid': row.id}
                ).scalar()
                if eligible_location:
                    raw_items.append({
                        'criteria_type': 'location',
                        'criteria_key': 'study_state',
                        'required_value': eligible_location
                    })

            if has_origin_country or has_origin_country_alt:
                origin_col = 'student_origin_country' if has_origin_country else 'student_country_of_origin'
                origin_country = conn.execute(
                    text(f'SELECT {origin_col} FROM scholarships WHERE id = :sid'),
                    {'sid': row.id}
                ).scalar()
                if origin_country:
                    raw_items.append({
                        'criteria_type': 'demographic',
                        'criteria_key': 'nationality',
                        'required_value': origin_country
                    })

            if not raw_items:
                snippet = raw_text.strip()[:255]
                if snippet:
                    raw_items = [{
                        'criteria_type': 'other',
                        'criteria_key': 'raw_text',
                        'required_value': snippet,
                        'is_required': False
                    }]
                else:
                    raw_items = [{
                        'criteria_type': 'other',
                        'criteria_key': 'raw_text',
                        'required_value': 'Eligibility pending',
                        'is_required': False
                    }]
                if not args.replace and existing_count:
                    skipped += 1
                    continue
            if existing_count and not args.replace:
                skipped += 1
                continue
            if args.replace and existing_count:
                conn.execute(
                    text('DELETE FROM eligibility_criteria WHERE scholarship_id = :sid'),
                    {'sid': row.id}
                )

            inserted_for_scholarship = 0
            seen = set()
            for raw_item in raw_items:
                criteria_type, criteria_key, required_value, is_required = coerce_criteria_row(raw_item)
                if not criteria_type or not required_value:
                    continue
                normalized_type = normalize_criteria_type(criteria_type)
                normalized_key = normalize_criteria_key(criteria_key)
                if not normalized_key and normalized_type in {'location', 'demographic'}:
                    continue
                if not normalized_key:
                    normalized_key = normalize_criteria_key(normalized_type)
                if not validate_criteria_key(normalized_type, normalized_key):
                    continue
                dedupe_key = (
                    normalized_type,
                    normalized_key,
                    str(required_value).strip().lower()
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                result = conn.execute(text('''
                    INSERT IGNORE INTO eligibility_criteria
                    (scholarship_id, criteria_type, criteria_key, required_value, is_required)
                    VALUES
                    (:scholarship_id, :criteria_type, :criteria_key, :required_value, :is_required)
                '''), {
                    'scholarship_id': row.id,
                    'criteria_type': normalized_type,
                    'criteria_key': normalized_key,
                    'required_value': str(required_value).strip(),
                    'is_required': bool(True if is_required is None else is_required)
                })
                if result.rowcount == 0:
                    continue
                inserted += 1
                inserted_for_scholarship += 1

            if inserted_for_scholarship == 0:
                result = conn.execute(text('''
                    INSERT IGNORE INTO eligibility_criteria
                    (scholarship_id, criteria_type, criteria_key, required_value, is_required)
                    VALUES
                    (:scholarship_id, :criteria_type, :criteria_key, :required_value, :is_required)
                '''), {
                    'scholarship_id': row.id,
                    'criteria_type': 'other',
                    'criteria_key': 'raw_text',
                    'required_value': 'Eligibility pending',
                    'is_required': False
                })
                if result.rowcount:
                    inserted += 1

    logging.info('Inserted %s eligibility criteria rows. Skipped %s scholarships.', inserted, skipped)
    print(f'Inserted {inserted} eligibility criteria rows. Skipped {skipped} scholarships.')


if __name__ == '__main__':
    main()
