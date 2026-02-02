import re

from sqlalchemy import text

from db import engine


INDUSTRY_PATTERNS = [
    ('law', r'\blaw|legal|juris|jurisdiction|barrister|solicitor|attorney\b'),
    ('health', r'\bhealth|medical|medicine|nursing|midwif|pharma|public health|clinical\b'),
    ('education', r'\beducation|teaching|teacher|pedagogy|curriculum\b'),
    ('business', r'\bbusiness|commerce|accounting|finance|economics|management|marketing|entrepreneur\b'),
    ('stem', r'\bstem|engineering|computer|software|it\b|information technology|data science|science|technology|math|mathematics\b'),
    ('arts', r'\barts?|design|creative|music|film|media|theatre|drama\b'),
    ('humanities', r'\bhumanities|history|philosophy|languages?|literature|sociology|psychology\b'),
]


def extract_industry(texts):
    for text in texts:
        if not text:
            continue
        for industry, pattern in INDUSTRY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return industry
    return None


def main():
    with engine.connect() as conn:
        scholarships = conn.execute(text('''
            SELECT id, title, description, industry
            FROM scholarships
        ''')).fetchall()

        criteria_rows = conn.execute(text('''
            SELECT scholarship_id, required_value, criteria_type
            FROM eligibility_criteria
            WHERE criteria_type IN ('demographic', 'demographics', 'location', 'other', 'field_of_study')
        ''')).fetchall()

        criteria_map = {}
        for row in criteria_rows:
            criteria_map.setdefault(row.scholarship_id, []).append(row.required_value)

        updated_industry = 0
        skipped = 0

        for row in scholarships:
            texts = []
            texts.extend(criteria_map.get(row.id, []))
            if row.description:
                texts.append(row.description)
            if row.title:
                texts.append(row.title)

            updates = {}

            if not row.industry:
                industry = extract_industry(texts)
                if industry:
                    updates['industry'] = industry

            if not updates:
                skipped += 1
                continue

            updates['scholarship_id'] = row.id
            set_clauses = ', '.join([f"{key} = :{key}" for key in updates if key != 'scholarship_id'])
            conn.execute(
                text(f'''
                    UPDATE scholarships
                    SET {set_clauses}
                    WHERE id = :scholarship_id
                '''),
                updates
            )

            if 'industry' in updates:
                updated_industry += 1

        conn.commit()

    print(
        f'Updated industry for {updated_industry} scholarships. '
        f'Skipped {skipped}.'
    )


if __name__ == '__main__':
    main()
