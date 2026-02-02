import argparse
import json
import logging
import os
import time

from sqlalchemy import text, bindparam
from dotenv import load_dotenv

from db import engine
from perplexity_import import call_perplexity


PROMPT_TEMPLATE = (
    "You are extracting scholarship eligibility from a single scholarship page. "
    "Use the application URL below as the only source. "
    "Return JSON only with these keys:\n"
    "- eligibility_raw_text: a concise copy of the eligibility section text "
    "(bullet points ok, preserve meaning)\n"
    "- eligibility_criteria: list of objects with criteria_type, criteria_key, "
    "required_value, is_required (true if required, false if optional)\n\n"
    "criteria_type values: academic_level|gpa|field_of_study|demographic|location|"
    "financial_need|extracurricular|other\n"
    "criteria_key values: for location use study_state; for demographic use "
    "residency_status or nationality; otherwise use a short specific key.\n\n"
    "Application URL:\n{application_url}"
)


def main():
    parser = argparse.ArgumentParser(
        description='Re-scrape eligibility_raw_text for scholarships.'
    )
    parser.add_argument(
        '--ids',
        help='Comma-separated scholarship IDs to process.'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of scholarships to process.'
    )
    parser.add_argument(
        '--sleep',
        type=float,
        default=0.5,
        help='Seconds to sleep between requests.'
    )
    args = parser.parse_args()

    load_dotenv()

    ids = []
    if args.ids:
        ids = [item.strip() for item in args.ids.split(',') if item.strip()]

    with engine.begin() as conn:
        if ids:
            stmt = text('''
                SELECT id, application_url
                FROM scholarships
                WHERE id IN :ids
            ''').bindparams(bindparam('ids', expanding=True))
            rows = conn.execute(
                stmt,
                {'ids': [int(item) for item in ids]}
            ).fetchall()
        else:
            rows = conn.execute(text('''
                SELECT id, application_url
                FROM scholarships
                WHERE (eligibility_raw_text IS NULL OR eligibility_raw_text = '')
                AND application_url IS NOT NULL
                AND application_url != ''
            ''')).fetchall()

        if args.limit:
            rows = rows[:args.limit]

        updated = 0
        failed = 0

        for row in rows:
            prompt = PROMPT_TEMPLATE.format(application_url=row.application_url)
            try:
                response, raw_content = call_perplexity(prompt)
            except Exception as exc:
                logging.exception('Perplexity request failed for %s: %s', row.id, exc)
                failed += 1
                continue

            eligibility_raw_text = response.get('eligibility_raw_text', '')
            if not eligibility_raw_text:
                eligibility_raw_text = ''

            conn.execute(
                text('''
                    UPDATE scholarships
                    SET eligibility_raw_text = :eligibility_raw_text
                    WHERE id = :scholarship_id
                '''),
                {
                    'eligibility_raw_text': eligibility_raw_text,
                    'scholarship_id': row.id
                }
            )
            debug_path = os.getenv(
                'PERPLEXITY_LAST_RESPONSE_FILE',
                'perplexity_last_response.txt'
            )
            with open(debug_path, 'w', encoding='utf-8') as handle:
                handle.write(raw_content)

            updated += 1
            time.sleep(args.sleep)

    print(f'Updated {updated} scholarships. Failed {failed}.')


if __name__ == '__main__':
    main()
