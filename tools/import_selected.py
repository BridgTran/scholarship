#!/usr/bin/env python3
"""
Import 7 selected scholarships with manual corrections applied.
Run from the project root: python3 tools/import_selected.py
"""
import json, sys, time, os, logging, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

from sqlalchemy import text
from db import engine
from tools.import_pipeline import (
    fetch_url, extract_scholarship_bs4, confidence_score,
    extract_main_text, call_claude, CONFIDENCE_THRESHOLD,
    _insert_scholarships_from_list, quality_score,
)

PROMPT_PATH = 'perplexity_prompt.txt'

# Map common month names to last-day of month for deadline fallback
_MONTH_MAP = {
    'january': '01', 'february': '02', 'march': '03', 'april': '04',
    'may': '05', 'june': '06', 'july': '07', 'august': '08',
    'september': '09', 'october': '10', 'november': '11', 'december': '12',
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10',
    'nov': '11', 'dec': '12',
}
_MONTH_LAST_DAY = {
    '01': '31', '02': '28', '03': '31', '04': '30', '05': '31', '06': '30',
    '07': '31', '08': '31', '09': '30', '10': '31', '11': '30', '12': '31',
}


def _parse_deadline(raw) -> str | None:
    """Try to coerce a deadline string into YYYY-MM-DD. Returns None if hopeless."""
    if not raw:
        return None
    s = str(raw).strip()
    # Already YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', s)
    if m:
        return f'{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}'
    # Month YYYY  e.g. "March 2026"
    m = re.match(r'^([A-Za-z]+)\s+(\d{4})$', s)
    if m:
        mon = _MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f'{m.group(2)}-{mon}-{_MONTH_LAST_DAY[mon]}'
    # YYYY-MM
    m = re.match(r'^(\d{4})-(\d{2})$', s)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{_MONTH_LAST_DAY.get(m.group(2), "30")}'
    # Just a year e.g. "2026"
    m = re.match(r'^(\d{4})$', s)
    if m:
        return f'{m.group(1)}-12-31'
    return None


def sanitize_scholarship(s: dict) -> dict:
    """Fix common extraction issues before validation / insertion.

    scholarship_type remapping and quality scoring are handled downstream
    by _insert_scholarships_from_list() in import_pipeline.py.
    """
    # amount: reject sentinel values < $100
    amt = s.get('amount')
    if amt is not None:
        try:
            amt_f = float(amt)
            if 0 < amt_f < 100:
                logging.info('  Ignoring suspiciously small amount $%.0f — zeroing out', amt_f)
                s['amount'] = 0
        except (TypeError, ValueError):
            pass

    # deadline: coerce to YYYY-MM-DD; fallback to end-of-year if unparseable
    raw_deadline = s.get('deadline')
    parsed = _parse_deadline(raw_deadline)
    if parsed != raw_deadline:
        logging.info('  Deadline "%s" → "%s"', raw_deadline, parsed or '2026-12-31')
    s['deadline'] = parsed or '2026-12-31'

    # organization.type: default to 'Private' if missing (normalize_org_type handles mapping)
    org = s.get('organization')
    if isinstance(org, dict) and not org.get('type'):
        logging.info('  org.type missing — defaulting to "Private"')
        org['type'] = 'Private'

    # description: ensure non-empty
    if not s.get('description'):
        s['description'] = s.get('title', 'No description available.')

    return s


FREEMASONS_NOTE = (
    ' No Freemasons family connection is required — '
    'this scholarship is open to any eligible student based on financial need '
    'and community involvement.'
)

# ---------------------------------------------------------------------------
# URLs to import and the title filter/key to identify each one
# ---------------------------------------------------------------------------
TARGETS = [
    # Add new import targets here. Clear after each run to avoid re-importing.
]

# ---------------------------------------------------------------------------
# Legacy targets (already imported — kept for reference, not re-run)
# ---------------------------------------------------------------------------
_LEGACY_TARGETS = [
    {
        'url': 'https://www.nswtf.org.au/news/2026/02/04/applications-now-open-for-federations-4000-future-teacher-scholarships/',
        'title_contains': 'Future Teacher',
        'overrides': {'status': 'active'},
    },
    {
        'url': 'https://www.nswnma.asn.au/education/scholarships/',
        'title_contains': 'Edith Cavell',
        'overrides': {'status': 'draft'},
    },
    {
        'url': 'https://www.nswnma.asn.au/education/scholarships/',
        'title_contains': 'Roz Norman',
        'overrides': {'status': 'draft'},
    },
    {
        'url': 'https://www.nswnma.asn.au/education/scholarships/',
        'title_contains': 'Lions Nurses',
        'overrides': {'status': 'draft'},
    },
    {
        'url': 'https://www.swinburne.edu.au/study/options/scholarships/421/freemasons-foundation-victoria-scholarship-2026/',
        'title_contains': 'Freemasons Foundation Victoria',
        'overrides': {
            'status': 'draft',
            'append_description': FREEMASONS_NOTE,
        },
    },
    {
        'url': 'https://www.swinburne.edu.au/study/options/scholarships/550/david-johnson-freemasons-foundation-scholarship-2026/',
        'title_contains': 'David Johnson',
        'overrides': {
            'status': 'draft',
            'append_description': FREEMASONS_NOTE,
            'org_name': 'Freemasons Foundation Victoria',
            'industry': 'Other',
        },
    },
    {
        'url': 'https://www.acu.edu.au/study-at-acu/fees-and-scholarships/find-a-scholarship/freemasons-foundation-scholarship',
        'title_contains': 'Freemasons Foundation',
        'overrides': {
            'status': 'draft',
            'append_description': FREEMASONS_NOTE,
        },
    },
]  # end _LEGACY_TARGETS

# ---------------------------------------------------------------------------
# Fetch + extract, cache per URL to avoid hitting the same page twice
# ---------------------------------------------------------------------------
url_cache: dict[str, list[dict]] = {}

def extract_url(url: str) -> list[dict]:
    if url in url_cache:
        return url_cache[url]
    logging.info('Fetching %s', url)
    try:
        html = fetch_url(url)
    except Exception as e:
        logging.error('Fetch failed: %s', e)
        url_cache[url] = []
        return []
    data  = extract_scholarship_bs4(html, url)
    score = confidence_score(data)
    if score >= CONFIDENCE_THRESHOLD:
        scholarships = [data]
        logging.info('  Heuristic OK (score=%.2f)', score)
    else:
        logging.info('  Heuristic %.2f < %.2f — calling Claude', score, CONFIDENCE_THRESHOLD)
        try:
            page_text    = extract_main_text(html)
            resp         = call_claude(page_text, url, PROMPT_PATH)
            scholarships = resp.get('scholarships', [])
        except Exception as e:
            logging.error('Claude failed: %s', e)
            scholarships = []
    for s in scholarships:
        s.setdefault('application_url', url)
    url_cache[url] = scholarships
    time.sleep(0.5)
    return scholarships

# ---------------------------------------------------------------------------
# Build the final list
# ---------------------------------------------------------------------------
selected: list[dict] = []

for target in TARGETS:
    url   = target['url']
    filt  = target['title_contains'].lower()
    overrides = target['overrides']

    scholarships = extract_url(url)
    match = next(
        (s for s in scholarships if filt in (s.get('title') or '').lower()),
        None
    )
    if match is None:
        logging.warning('Could not find "%s" in results from %s', target['title_contains'], url)
        continue

    # Deep-copy to avoid mutating cache
    import copy
    s = copy.deepcopy(match)

    # Apply overrides
    s['status'] = overrides.get('status', s.get('status', 'active'))

    if 'append_description' in overrides:
        s['description'] = (s.get('description') or '') + overrides['append_description']

    if 'org_name' in overrides and s.get('organization'):
        s['organization']['name'] = overrides['org_name']

    if 'industry' in overrides:
        s['industry'] = overrides['industry']

    if 'deadline' in overrides:
        s['deadline'] = overrides['deadline']

    if 'scholarship_type' in overrides:
        s['scholarship_type'] = overrides['scholarship_type']

    # Sanitize before validation
    s = sanitize_scholarship(s)

    logging.info('Prepared: [%s] %s (status=%s, deadline=%s, type=%s)',
                 s['status'], s.get('title'), s['status'],
                 s.get('deadline'), s.get('scholarship_type'))
    selected.append(s)

# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------
print(f'\n{"="*60}')
print(f'Prepared {len(selected)} scholarships for import:')
for s in selected:
    score, missing = quality_score(s)
    flag = ' ⚠ LOW QUALITY' if score < 60 else ''
    missing_str = f'  missing: {", ".join(missing)}' if missing else ''
    print(f'  [{s["status"]:6}] Q={score:3}/100{flag}  {s.get("title")}  —  ${s.get("amount") or s.get("benefits_text") or "?"}')
    if missing:
        print(f'           {missing_str}')

print(f'\nInserting into database...')

with engine.connect() as conn:
    trans = conn.begin()
    try:
        before_ids = {row[0] for row in conn.execute(text('SELECT id FROM scholarships')).fetchall()}
        inserted, skipped, invalid = _insert_scholarships_from_list(conn, selected)
        after_ids  = {row[0] for row in conn.execute(text('SELECT id FROM scholarships')).fetchall()}
        new_ids    = sorted(after_ids - before_ids)
        trans.commit()
    except Exception:
        trans.rollback()
        raise

print(f'\nDone.')
print(f'  Inserted:  {inserted}')
print(f'  Skipped (duplicate): {skipped}')
print(f'  Skipped (invalid):   {invalid}')
print(f'  New IDs: {new_ids}')
