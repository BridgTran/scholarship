#!/usr/bin/env python3
"""
Scholarship Import Pipeline

Consolidates: perplexity_import.py, perplexity_scrape_urls.py,
              rescrape_eligibility_raw.py, automated_import.py

Discovery uses the Serper API (Google search) to find scholarship URLs.
Extraction uses BeautifulSoup for heuristic parsing, with Claude API as a
fallback for pages where confidence is below the threshold.

Usage:
    # Discover scholarships via Google search (Serper) + Claude extraction
    python tools/import_pipeline.py discover

    # Scrape from a text file of URLs (one per line)
    python tools/import_pipeline.py from-urls urls.txt

    # Re-scrape eligibility_raw_text for existing records
    python tools/import_pipeline.py rescrape --ids 147,148
    python tools/import_pipeline.py rescrape --limit 10

    # Full pipeline: discover → collect sources → normalize → validate
    python tools/import_pipeline.py run
    python tools/import_pipeline.py run --dry-run

    # Full pipeline on existing IDs (skip discovery)
    python tools/import_pipeline.py run --ids 147,148

Environment variables (.env):
    SERPER_API_KEY              — required for 'discover' subcommand
    ANTHROPIC_API_KEY           — required for Claude extraction fallback
    CLAUDE_MODEL                — optional (default: claude-haiku-4-5-20251001)
    EXTRACTION_PROMPT_FILE      — optional (default: perplexity_prompt.txt)
    EXTRACTION_CONFIDENCE_THRESHOLD — optional float 0–1 (default: 0.85)
"""

import argparse
import json
import logging
import os
import re
import ssl
import subprocess
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from urllib import request as urlrequest
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import certifi
except ImportError:
    certifi = None

from dotenv import load_dotenv
from sqlalchemy import text, bindparam

from db import engine
from criteria_utils import (
    normalize_criteria_type,
    normalize_criteria_key,
    normalize_criteria_value,
    validate_criteria_key,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)

# ── Constants ────────────────────────────────────────────────────────────────

ALLOWED_ORG_TYPES = {'Government', 'University', 'Private', 'Foundation', 'Nonprofit'}
ALLOWED_STATUSES  = {'active', 'expired', 'draft', 'suspended', 'inactive'}

YEAR_CODES       = {'YEAR_1', 'YEAR_2', 'YEAR_3', 'YEAR_4', 'FINAL_YEAR'}
COMPOUND_YEAR_RE = re.compile(r'\s*(?:\bor\b|,|/)\s*', re.IGNORECASE)

CONFIDENCE_THRESHOLD = float(os.getenv('EXTRACTION_CONFIDENCE_THRESHOLD', '0.85'))

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-AU,en;q=0.9',
}

SKIP_TAGS = {'script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside'}

CONTENT_ATTRS = re.compile(
    r'content|main|article|body|primary|page|scholarship|eligib',
    re.IGNORECASE,
)

BOILERPLATE_RE = [
    re.compile(r'\bquick links?\b', re.IGNORECASE),
    re.compile(r'\bcricos\b',       re.IGNORECASE),
    re.compile(r'\bteqsa\b',        re.IGNORECASE),
]

# Serper queries for Australian scholarship discovery
DISCOVERY_QUERIES = [
    'Australian undergraduate scholarship 2025 apply eligibility',
    'scholarship grant Australia university 2025 site:edu.au',
    'postgraduate scholarship Australia 2025 applications open',
    'Indigenous Australian scholarship 2025 university',
    'need-based scholarship Australia 2025 financial hardship',
    'merit scholarship Australian university 2025',
    'rural regional scholarship Australia 2025 students',
    'women STEM scholarship Australia 2025',
    'disability scholarship Australia university 2025',
    'first generation university scholarship Australia 2025',
]

# Heuristic extraction patterns
_AMOUNT_RE   = re.compile(r'\$\s*([\d,]+(?:\.\d{2})?)', re.IGNORECASE)
_DEADLINE_RE = re.compile(
    r'(?:deadline|closes?|due|applications?\s+(?:close|due))[:\s]+'
    r'(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2}|\w+\s+\d{1,2},?\s+\d{4})',
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


# ── HTTP Fetching ─────────────────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 30) -> bytes:
    """Fetch a URL and return raw bytes. Raises on failure."""
    if HAS_HTTPX:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content

    # Fallback: curl → urllib
    curl_cmd = [
        'curl', '--location', '--silent', '--show-error',
        '--max-time', str(timeout),
        '--user-agent', HEADERS['User-Agent'],
        '--compressed', url,
    ]
    try:
        result = subprocess.run(curl_cmd, check=False,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass

    req = urlrequest.Request(url, headers={'User-Agent': HEADERS['User-Agent']})
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except ssl.SSLError:
        ctx = ssl.create_default_context()
        with urlrequest.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read()


def _find_content_element(soup):
    if (el := soup.find('main')):
        return el
    if (el := soup.find('article')):
        return el
    for tag in ('section', 'div'):
        for attr in ('id', 'class'):
            el = soup.find(tag, attrs={attr: CONTENT_ATTRS})
            if el:
                return el
    return soup.find('body')


def extract_main_text(html_bytes: bytes) -> str:
    """Extract clean main-content text from HTML bytes."""
    if HAS_BS4:
        soup = BeautifulSoup(html_bytes, 'lxml')
        for tag in SKIP_TAGS:
            for el in soup.find_all(tag):
                el.decompose()
        content = _find_content_element(soup)
        raw = content.get_text(separator='\n') if content else ''
    else:
        html = html_bytes.decode('utf-8', errors='ignore')
        raw = re.sub(r'<[^>]+>', ' ', html)

    seen, lines = set(), []
    for line in raw.splitlines():
        norm = ' '.join(line.split())
        if not norm:
            continue
        if any(p.search(norm) for p in BOILERPLATE_RE):
            continue
        key = norm.lower()
        if key not in seen:
            seen.add(key)
            lines.append(norm)
    return '\n'.join(lines)


# ── Serper API ────────────────────────────────────────────────────────────────

def search_serper(query: str, num_results: int = 10) -> list[str]:
    """Search via Serper (Google) API. Returns a list of result URLs."""
    api_key = os.getenv('SERPER_API_KEY')
    if not api_key:
        raise RuntimeError('SERPER_API_KEY not set in .env')

    payload = json.dumps({
        'q':   query,
        'num': num_results,
        'gl':  'au',
    }).encode('utf-8')

    req = urlrequest.Request(
        'https://google.serper.dev/search',
        data=payload,
        headers={
            'X-API-KEY':    api_key,
            'Content-Type': 'application/json',
        },
    )
    ssl_ctx = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    with urlrequest.urlopen(req, context=ssl_ctx, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    return [r['link'] for r in data.get('organic', []) if r.get('link')]


# ── Claude API ────────────────────────────────────────────────────────────────

def load_prompt(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read().strip()


def extract_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    raise ValueError('Response did not contain valid JSON.')


def call_claude(page_text: str, url: str, prompt_path: str) -> dict:
    """Extract structured scholarship data from page text using Claude."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError('anthropic package not installed. Run: pip install anthropic')

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set in .env')

    model       = os.getenv('CLAUDE_MODEL', 'claude-haiku-4-5-20251001')
    base_prompt = load_prompt(prompt_path)

    full_prompt = (
        f"{base_prompt}\n\n"
        f"Source URL: {url}\n\n"
        "Extract scholarship data from the page content below. "
        "Return a JSON object with a 'scholarships' array (may contain 1 or more entries).\n\n"
        f"Page content:\n{page_text[:6000]}"
    )

    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{'role': 'user', 'content': full_prompt}],
    )
    return extract_json(message.content[0].text)


# ── Heuristic extraction + confidence scoring ─────────────────────────────────

def _parse_date(raw: str) -> str | None:
    """Try to normalise a raw date string to YYYY-MM-DD."""
    raw = raw.strip()
    if _ISO_DATE_RE.match(raw):
        return raw
    from datetime import datetime as dt
    for fmt in ('%d %B %Y', '%d %b %Y', '%B %d, %Y', '%B %d %Y', '%b %d %Y'):
        try:
            return dt.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def extract_scholarship_bs4(html_bytes: bytes, url: str) -> dict:
    """Heuristic extraction — returns a partial scholarship dict (no AI).

    Used to decide whether Claude is needed. Any field not found is simply
    absent from the returned dict.
    """
    if not HAS_BS4:
        return {}

    soup = BeautifulSoup(html_bytes, 'lxml')
    for tag in SKIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    data: dict = {}

    # Title from <h1>
    h1 = soup.find('h1')
    if h1:
        data['title'] = h1.get_text(strip=True)[:200]

    # Description — first paragraph > 80 chars
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 80:
            data['description'] = text[:500]
            break

    full_text = soup.get_text()

    # Dollar amount
    m = _AMOUNT_RE.search(full_text)
    if m:
        try:
            data['amount'] = float(m.group(1).replace(',', ''))
        except ValueError:
            pass

    # Deadline
    m = _DEADLINE_RE.search(full_text)
    if m:
        parsed = _parse_date(m.group(1))
        if parsed:
            data['deadline'] = parsed

    # Organisation inferred from domain
    hostname = urlparse(url).hostname or ''
    if hostname:
        parts    = hostname.replace('www.', '').split('.')
        org_name = parts[0].replace('-', ' ').title()
        org_type = 'University' if 'edu' in hostname else 'Private'
        data['organization'] = {
            'name':    org_name,
            'type':    org_type,
            'website': f'https://{hostname}',
        }

    return data


def confidence_score(data: dict) -> float:
    """Score how complete the heuristically-extracted data is (0.0–1.0).

    Weights:
      title        0.30  — can't insert without a name
      deadline     0.30  — required by validate_scholarship()
      description  0.20  — required by validate_scholarship()
      amount       0.10
      organization 0.10
    """
    score = 0.0
    if data.get('title'):
        score += 0.30
    if data.get('deadline') and is_valid_date(data.get('deadline')):
        score += 0.30
    if data.get('description') and len(data.get('description', '')) > 50:
        score += 0.20
    if data.get('amount') and data.get('amount', 0) > 0:
        score += 0.10
    if isinstance(data.get('organization'), dict) and data['organization'].get('name'):
        score += 0.10
    return score


# ── DB helpers ───────────────────────────────────────────────────────────────

def normalize_org_type(value: str) -> str:
    mapping = {
        'government': 'Government', 'govt': 'Government',
        'university': 'University', 'college': 'University',
        'private': 'Private', 'company': 'Private', 'corporate': 'Private',
        'foundation': 'Foundation',
        'nonprofit': 'Nonprofit', 'non-profit': 'Nonprofit', 'ngo': 'Nonprofit',
    }
    raw = str(value or '').strip().lower()
    return mapping.get(raw, 'Private')


def is_valid_date(value) -> bool:
    return bool(value and re.match(r'^\d{4}-\d{2}-\d{2}$', str(value)))


def find_or_create_organization(conn, org: dict) -> int:
    name     = org.get('name')
    org_type = normalize_org_type(org.get('type'))
    if not name:
        raise ValueError('Organization name is required.')
    row = conn.execute(
        text('SELECT id FROM organizations WHERE name = :name AND type = :type LIMIT 1'),
        {'name': name, 'type': org_type},
    ).first()
    if row:
        return row.id
    result = conn.execute(
        text('''
            INSERT INTO organizations (name, type, website, jurisdiction_state, jurisdiction_country)
            VALUES (:name, :type, :website, :jurisdiction_state, :jurisdiction_country)
        '''),
        {
            'name':                 name,
            'type':                 org_type,
            'website':              org.get('website'),
            'jurisdiction_state':   org.get('jurisdiction_state') or org.get('offered_location'),
            'jurisdiction_country': org.get('jurisdiction_country'),
        },
    )
    return result.lastrowid


def insert_scholarship(conn, scholarship: dict, organization_id: int):
    """Insert a scholarship row. Returns new ID, or None if already exists."""
    status = str(scholarship.get('status', 'active')).strip().lower()
    if status not in ALLOWED_STATUSES:
        status = 'active'

    existing = conn.execute(
        text('''
            SELECT id FROM scholarships
            WHERE title = :title AND organization_id = :organization_id AND deadline = :deadline
            LIMIT 1
        '''),
        {
            'title':           scholarship['title'].strip(),
            'organization_id': organization_id,
            'deadline':        scholarship['deadline'],
        },
    ).first()
    if existing:
        return None

    eligibility_raw_text = scholarship.get('eligibility_raw_text')
    if not eligibility_raw_text and scholarship.get('eligibility_criteria'):
        eligibility_raw_text = json.dumps(scholarship['eligibility_criteria'], ensure_ascii=True)

    for field, col in [
        ('jurisdiction_state',   'jurisdiction_state'),
        ('jurisdiction_country', 'jurisdiction_country'),
    ]:
        value = scholarship.get(field) or scholarship.get('offered_location')
        if value:
            conn.execute(
                text(f'''
                    UPDATE organizations SET {col} = :{col}
                    WHERE id = :org_id AND ({col} IS NULL OR {col} = '')
                '''),
                {col: value, 'org_id': organization_id},
            )

    result = conn.execute(
        text('''
            INSERT INTO scholarships
            (title, description, amount, deadline, organization_id, application_url,
             status, industry, scholarship_type, requires_application,
             eligibility_raw_text, created_at)
            VALUES
            (:title, :description, :amount, :deadline, :organization_id, :application_url,
             :status, :industry, :scholarship_type, :requires_application,
             :eligibility_raw_text, NOW())
        '''),
        {
            'title':                scholarship['title'].strip(),
            'description':          scholarship['description'].strip(),
            'amount':               float(scholarship.get('amount') or 0),
            'deadline':             scholarship['deadline'],
            'organization_id':      organization_id,
            'application_url':      scholarship.get('application_url'),
            'status':               status,
            'industry':             scholarship.get('industry'),
            'scholarship_type':     scholarship.get('scholarship_type', 'Other'),
            'requires_application': bool(scholarship.get('requires_application', True)),
            'eligibility_raw_text': eligibility_raw_text,
        },
    )
    return result.lastrowid


def expand_compound_criteria(criteria_list: list) -> list:
    """Split year_of_study rows that contain multiple canonical year codes.

    e.g. value 'YEAR_2 or YEAR_3' → two rows. Safety net for LLM output.
    """
    expanded = []
    for c in criteria_list:
        key   = (c.get('criteria_key') or '').strip()
        value = (c.get('required_value') or '').strip()
        if key == 'year_of_study':
            parts = [p.strip() for p in COMPOUND_YEAR_RE.split(value) if p.strip()]
            if len(parts) > 1 and all(p in YEAR_CODES for p in parts):
                for part in parts:
                    expanded.append({**c, 'required_value': part})
                continue
        expanded.append(c)
    return expanded


def insert_criteria(conn, scholarship_id: int, criteria: dict, source_url: str = None):
    """Normalise and insert one eligibility criterion row."""
    criteria_type = normalize_criteria_type(
        criteria.get('criteria_type'),
        scholarship_id=scholarship_id,
        source_url=source_url,
        criteria=criteria,
    )
    criteria_key = normalize_criteria_key(criteria.get('criteria_key'))
    if not criteria_key and criteria_type in {'location', 'demographic'}:
        raise ValueError('Eligibility criteria must include criteria_key')
    if not criteria_key:
        criteria_key = normalize_criteria_key(criteria_type)
    if not validate_criteria_key(criteria_type, criteria_key):
        raise ValueError(f'Invalid criteria_key "{criteria_key}" for type "{criteria_type}"')

    criteria_value = normalize_criteria_value(
        criteria_type, criteria_key,
        str(criteria.get('required_value', '')).strip(),
    )
    conn.execute(
        text('''
            INSERT INTO eligibility_criteria
            (scholarship_id, criteria_type, criteria_key, required_value, is_required,
             inclusion_keywords, exclusion_keywords)
            VALUES
            (:scholarship_id, :criteria_type, :criteria_key, :required_value, :is_required,
             :inclusion_keywords, :exclusion_keywords)
        '''),
        {
            'scholarship_id':     scholarship_id,
            'criteria_type':      criteria_type,
            'criteria_key':       criteria_key,
            'required_value':     criteria_value,
            'is_required':        bool(criteria.get('is_required', True)),
            'inclusion_keywords': criteria.get('inclusion_keywords'),
            'exclusion_keywords': criteria.get('exclusion_keywords'),
        },
    )


def validate_scholarship(scholarship: dict) -> bool:
    for field in ['title', 'description', 'deadline', 'organization']:
        if not scholarship.get(field):
            return False
    org = scholarship['organization']
    if not org.get('name') or not org.get('type'):
        return False
    if not is_valid_date(scholarship.get('deadline')):
        return False
    return True


def _insert_scholarships_from_list(conn, scholarships: list) -> tuple[int, int, int]:
    """Shared insertion loop. Returns (inserted, skipped_dupes, skipped_invalid)."""
    inserted, skipped, skipped_invalid = 0, 0, 0
    for scholarship in scholarships:
        if not validate_scholarship(scholarship):
            logging.warning('Skipping invalid scholarship: %s', scholarship.get('title'))
            skipped_invalid += 1
            continue
        try:
            org_id         = find_or_create_organization(conn, scholarship['organization'])
            scholarship_id = insert_scholarship(conn, scholarship, org_id)
            if scholarship_id is None:
                skipped += 1
                continue
            criteria_list = expand_compound_criteria(scholarship.get('eligibility_criteria', []))
            if not criteria_list:
                criteria_list = [{'criteria_type': 'other', 'criteria_key': 'raw_text',
                                  'required_value': 'Eligibility pending', 'is_required': True}]
            for c in criteria_list:
                try:
                    insert_criteria(conn, scholarship_id, c,
                                    source_url=scholarship.get('application_url'))
                except Exception:
                    logging.exception('Failed to insert criteria for scholarship %d: %s',
                                      scholarship_id, c)
            inserted += 1
            logging.info('Inserted scholarship %d: %s', scholarship_id, scholarship['title'])
        except Exception:
            logging.exception('Failed to insert scholarship: %s', scholarship.get('title'))
            skipped_invalid += 1
    return inserted, skipped, skipped_invalid


# ── Import modes ─────────────────────────────────────────────────────────────

def do_discover(prompt_path: str, batch_size: int = 10, batch_total: int = 5) -> list[int]:
    """Discover scholarship URLs via Serper (Google) search, then extract and insert.

    batch_total = number of queries to run from DISCOVERY_QUERIES
    batch_size  = results per query (Serper 'num' parameter)
    """
    queries   = DISCOVERY_QUERIES[:batch_total]
    all_urls: list[str] = []

    for query in queries:
        logging.info('Searching: %s', query)
        try:
            urls = search_serper(query, num_results=batch_size)
            all_urls.extend(urls)
            logging.info('  Found %d results', len(urls))
        except Exception:
            logging.exception('Serper search failed for: %s', query)
        time.sleep(0.3)  # be polite to the API

    # Deduplicate while preserving order
    all_urls = list(dict.fromkeys(all_urls))

    # Filter URLs already in the database
    with engine.connect() as conn:
        existing_urls = {
            row[0] for row in conn.execute(
                text('SELECT application_url FROM scholarships WHERE application_url IS NOT NULL')
            ).fetchall()
        }

    new_urls = [u for u in all_urls if u not in existing_urls]
    logging.info('Discovered %d new URLs after filtering %d already-known',
                 len(new_urls), len(all_urls) - len(new_urls))

    if not new_urls:
        logging.info('No new URLs to process.')
        return []

    return do_from_urls(new_urls, prompt_path)


def do_from_urls(urls: list[str], prompt_path: str, insert: bool = True) -> list[int]:
    """Fetch each URL, extract scholarship data, and insert into the database.

    Strategy per URL:
      1. Fetch HTML with httpx (or fallback).
      2. Run heuristic BeautifulSoup extraction.
      3. Score confidence. If >= CONFIDENCE_THRESHOLD, use the heuristic data.
      4. Otherwise, call Claude API with the page text.
    """
    all_scholarships: list[dict] = []

    for url in urls:
        logging.info('Processing %s ...', url)
        html_bytes = b''
        try:
            html_bytes = fetch_url(url)
        except Exception:
            logging.exception('Failed to fetch: %s', url)
            continue

        # Try heuristic first
        data  = extract_scholarship_bs4(html_bytes, url)
        score = confidence_score(data)

        if score >= CONFIDENCE_THRESHOLD:
            logging.info('  Heuristic extraction succeeded (score=%.2f)', score)
            scholarships = [data]
        else:
            logging.info('  Heuristic score %.2f < %.2f — calling Claude ...',
                         score, CONFIDENCE_THRESHOLD)
            try:
                page_text    = extract_main_text(html_bytes)
                response     = call_claude(page_text, url, prompt_path)
                scholarships = response.get('scholarships', [])
            except Exception:
                logging.exception('Claude extraction failed for: %s', url)
                continue

        for s in scholarships:
            s.setdefault('application_url', url)
        all_scholarships.extend(scholarships)
        time.sleep(0.5)

    if not insert or not all_scholarships:
        return []

    new_ids: list[int] = []
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            before_ids = {row[0] for row in conn.execute(text('SELECT id FROM scholarships')).fetchall()}
            _insert_scholarships_from_list(conn, all_scholarships)
            after_ids  = {row[0] for row in conn.execute(text('SELECT id FROM scholarships')).fetchall()}
            new_ids    = sorted(after_ids - before_ids)
            trans.commit()
        except Exception:
            trans.rollback()
            raise

    return new_ids


def _scholarship_criteria_snapshot(conn, scholarship_id: int) -> dict:
    """Return current criteria state for a scholarship (used for diff display)."""
    rows = conn.execute(
        text('''
            SELECT criteria_type, criteria_key, required_value
            FROM eligibility_criteria
            WHERE scholarship_id = :sid
            ORDER BY criteria_type, criteria_key
        '''),
        {'sid': scholarship_id},
    ).fetchall()
    return {
        'count': len(rows),
        'types': sorted({r.criteria_type for r in rows}),
        'rows':  [(r.criteria_type, r.criteria_key, r.required_value) for r in rows],
    }


def _replace_criteria(conn, scholarship_id: int, criteria_list: list,
                      source_url: str = None) -> tuple[int, int]:
    """Delete existing criteria and insert the new list.

    Returns (inserted, failed).
    """
    conn.execute(
        text('DELETE FROM eligibility_criteria WHERE scholarship_id = :sid'),
        {'sid': scholarship_id},
    )
    inserted, failed = 0, 0
    for c in expand_compound_criteria(criteria_list):
        try:
            insert_criteria(conn, scholarship_id, c, source_url=source_url)
            inserted += 1
        except Exception:
            logging.exception('Failed to insert criterion for scholarship %d: %s',
                              scholarship_id, c)
            failed += 1
    return inserted, failed


def _extract_criteria_free(page_text: str) -> list[dict]:
    """Run rule-based eligibility extraction without any API calls.

    Imports and uses the pattern-matching functions from normalize_eligibility.py.
    Returns a list of raw criteria dicts (same shape as Claude would return).
    """
    from tools.normalize_eligibility import (
        extract_sectioned_rules,
        extract_page_exclusions,
        clean_source_text,
    )
    cleaned = clean_source_text(page_text)
    criteria_rows, _benefits, _conditions, _amounts, manual_notes = \
        extract_sectioned_rules(cleaned)

    from tools.normalize_eligibility import append_criteria
    for note in manual_notes:
        trimmed = note[:255].strip()
        if trimmed:
            append_criteria(
                criteria_rows, 'other', 'manual_review_note', trimmed, True,
                sentence=note, detect_exclusion=False,
            )

    criteria_rows.extend(extract_page_exclusions(cleaned))
    return criteria_rows


def do_rescrape(
    ids: list[int] = None,
    limit: int = None,
    sleep: float = 0.5,
    prompt_path: str = None,
    order_by_fewest: bool = True,
    include_complete: bool = False,
    dry_run: bool = False,
    use_claude: bool = True,
) -> dict:
    """Re-scrape and rebuild eligibility criteria for existing scholarship records.

    Fetches each application URL, calls Claude for structured extraction, then
    replaces both eligibility_raw_text and all eligibility_criteria rows.

    Args:
        ids:              Specific scholarship IDs to process (overrides query).
        limit:            Cap the number of scholarships processed.
        sleep:            Seconds to wait between API calls.
        prompt_path:      Path to the extraction prompt file.
        order_by_fewest:  Process scholarships with fewest criteria first (default True).
        include_complete: Also rescrape scholarships that already have 5+ criteria.
        dry_run:          Print what would change without making any DB writes.

    Returns a summary dict with keys: updated, failed, skipped.
    """
    if prompt_path is None:
        prompt_path = os.getenv('EXTRACTION_PROMPT_FILE', 'perplexity_prompt.txt')

    # ── Build target list ────────────────────────────────────────────────────

    with engine.connect() as conn:
        if ids:
            stmt = text('''
                SELECT s.id, s.title, s.application_url,
                       COUNT(ec.id) AS criteria_count
                FROM scholarships s
                LEFT JOIN eligibility_criteria ec ON ec.scholarship_id = s.id
                WHERE s.id IN :ids
                GROUP BY s.id, s.title, s.application_url
                ORDER BY criteria_count ASC, s.id ASC
            ''').bindparams(bindparam('ids', expanding=True))
            rows = conn.execute(stmt, {'ids': ids}).fetchall()
        else:
            having_clause = '' if include_complete else 'HAVING criteria_count < 5'
            rows = conn.execute(text(f'''
                SELECT s.id, s.title, s.application_url,
                       COUNT(ec.id) AS criteria_count
                FROM scholarships s
                LEFT JOIN eligibility_criteria ec ON ec.scholarship_id = s.id
                WHERE s.application_url IS NOT NULL AND s.application_url != ''
                GROUP BY s.id, s.title, s.application_url
                {having_clause}
                ORDER BY criteria_count ASC, s.id ASC
            ''')).fetchall()

    if not order_by_fewest:
        # Already ordered by fewest by default; reverse if caller wants natural ID order
        rows = sorted(rows, key=lambda r: r.id)

    if limit:
        rows = rows[:limit]

    # ── Dry-run display ──────────────────────────────────────────────────────

    if dry_run:
        sep = '=' * 80
        print(f'\n{sep}')
        print(f'RESCRAPE DRY-RUN  —  {len(rows)} scholarship(s) would be processed')
        if not include_complete:
            print('  (only scholarships with < 5 criteria; use --all to include complete ones)')
        if order_by_fewest:
            print('  (ordered by fewest criteria first)')
        print(sep)
        print(f'\n  {"ID":>4}  {"Criteria":>8}  {"Types present":<32}  Title')
        print(f'  {"--":>4}  {"--------":>8}  {"-------------":<32}  -----')

        with engine.connect() as conn:
            for r in rows:
                snap  = _scholarship_criteria_snapshot(conn, r.id)
                types = ', '.join(snap['types']) if snap['types'] else '—'
                print(f'  {r.id:>4}  {r.criteria_count:>8}  {types:<32}  {r.title[:45]}')

        print(f'\nTo apply: remove --dry-run and add --limit {len(rows)}\n')
        return {'updated': 0, 'failed': 0, 'skipped': 0, 'dry_run': True}

    # ── Live rescrape ────────────────────────────────────────────────────────

    mode_label = 'free (BS4 + rules, no API)' if not use_claude else 'Claude API'
    print(f'\nMode: {mode_label}')

    updated, failed, skipped = 0, 0, 0

    for i, row in enumerate(rows, 1):
        print(f'\n[{i}/{len(rows)}] ID {row.id} ({row.criteria_count} criteria): {row.title[:60]}')

        if not row.application_url:
            print('  No application_url — skipping')
            skipped += 1
            continue

        # Fetch page
        try:
            html_bytes = fetch_url(row.application_url)
            page_text  = extract_main_text(html_bytes)
        except Exception:
            logging.exception('  Fetch failed for scholarship %d', row.id)
            failed += 1
            continue

        # Extract criteria
        if use_claude:
            try:
                response = call_claude(page_text, row.application_url, prompt_path)
            except Exception:
                logging.exception('  Claude extraction failed for scholarship %d', row.id)
                failed += 1
                continue
            if 'scholarships' in response and response['scholarships']:
                extracted = response['scholarships'][0]
            else:
                extracted = response
            eligibility_raw = extracted.get('eligibility_raw_text', '')
            new_criteria    = extracted.get('eligibility_criteria', [])
        else:
            # Free path — rule-based, zero API calls
            try:
                new_criteria    = _extract_criteria_free(page_text)
                eligibility_raw = page_text[:4000]
            except Exception:
                logging.exception('  Free extraction failed for scholarship %d', row.id)
                failed += 1
                continue

        # Snapshot before
        with engine.connect() as snap_conn:
            before = _scholarship_criteria_snapshot(snap_conn, row.id)

        # Write changes
        with engine.begin() as conn:
            if eligibility_raw:
                conn.execute(
                    text('UPDATE scholarships SET eligibility_raw_text = :txt WHERE id = :id'),
                    {'txt': eligibility_raw, 'id': row.id},
                )

            if new_criteria:
                ins, _fail = _replace_criteria(
                    conn, row.id, new_criteria,
                    source_url=row.application_url,
                )
                after_count = ins
            else:
                after_count = before['count']

        # Report diff
        delta = after_count - before['count']
        sign  = '+' if delta >= 0 else ''
        print(f'  criteria: {before["count"]} → {after_count} ({sign}{delta})')
        if new_criteria:
            types_found = sorted({c.get('criteria_type', '?') for c in new_criteria})
            print(f'  types: {", ".join(types_found)}')
        else:
            print('  (no criteria extracted — raw text updated only)')

        updated += 1
        if i < len(rows):
            time.sleep(sleep)

    print(f'\nRescrape complete: updated={updated}  failed={failed}  skipped={skipped}')
    return {'updated': updated, 'failed': failed, 'skipped': skipped}


# ── Validation helpers ────────────────────────────────────────────────────────

class ImportReport:
    def __init__(self):
        self.imported_ids       = []
        self.flags              = []
        self.errors             = []
        self.duplicates_skipped = 0
        self.invalid_skipped    = 0

    def add_flag(self, scholarship_id, flag_type, message, severity='WARNING'):
        self.flags.append({
            'scholarship_id': scholarship_id,
            'type':           flag_type,
            'message':        message,
            'severity':       severity,
        })

    def add_error(self, scholarship_id, error_message):
        self.errors.append({'scholarship_id': scholarship_id, 'error': error_message})

    def print_summary(self):
        sep = '=' * 80
        print(f'\n{sep}\nIMPORT REPORT\n{sep}')
        print(f'Imported:           {len(self.imported_ids)} scholarships')
        print(f'Duplicates skipped: {self.duplicates_skipped}')
        print(f'Invalid skipped:    {self.invalid_skipped}')

        if self.flags:
            print(f'\nFLAGGED FOR REVIEW ({len(self.flags)} items)')
            print('-' * 80)
            by_id: dict = {}
            for f in self.flags:
                by_id.setdefault(f['scholarship_id'], []).append(f)
            for sid, flags in by_id.items():
                print(f'\n[ID {sid}]')
                for f in flags:
                    icon = 'ERROR' if f['severity'] == 'ERROR' else 'WARN '
                    print(f'  [{icon}] {f["type"]}: {f["message"]}')

        if self.errors:
            print(f'\nERRORS ({len(self.errors)})')
            print('-' * 80)
            for e in self.errors:
                print(f'  [ID {e["scholarship_id"]}] {e["error"]}')

        if self.imported_ids:
            flagged = sorted({f['scholarship_id'] for f in self.flags})
            if flagged:
                print(f'\nIDs requiring manual review: {", ".join(map(str, flagged))}')
        print(f'\n{sep}\n')

    def to_dict(self):
        return {
            'timestamp':    datetime.now().isoformat(),
            'imported_ids': self.imported_ids,
            'flags':        self.flags,
            'errors':       self.errors,
        }


def _check_duplicate_name(conn, title, org_id, threshold=0.85):
    rows = conn.execute(
        text('SELECT id, title FROM scholarships WHERE organization_id = :org_id'),
        {'org_id': org_id},
    ).fetchall()
    for row in rows:
        if SequenceMatcher(None, title.lower(), row.title.lower()).ratio() >= threshold:
            return row.id, row.title
    return None


def _check_duplicate_url(conn, url):
    if not url:
        return None
    row = conn.execute(
        text('SELECT id FROM scholarships WHERE application_url = :url'),
        {'url': url},
    ).fetchone()
    return row.id if row else None


def _validate_url_quality(url):
    if not url:
        return False, 'No URL'
    for suffix in ['/scholarships', '/international-scholarships',
                   '/financial-aid', '/admissions', '/fees-and-costs/scholarships']:
        if url.lower().rstrip('/').endswith(suffix):
            return False, f'Generic landing page: {suffix}'
    return True, 'OK'


def validate_imported(scholarship_ids: list[int]) -> ImportReport:
    report = ImportReport()
    report.imported_ids = scholarship_ids
    if not scholarship_ids:
        return report

    with engine.connect() as conn:
        for sid in scholarship_ids:
            row = conn.execute(text('''
                SELECT s.title, s.application_url, s.organization_id
                FROM scholarships s WHERE s.id = :sid
            '''), {'sid': sid}).fetchone()
            if not row:
                report.add_error(sid, 'Not found in database')
                continue

            dup = _check_duplicate_name(conn, row.title, row.organization_id)
            if dup and dup[0] != sid:
                report.add_flag(sid, 'POSSIBLE_DUPLICATE',
                                 f'Similar to ID {dup[0]}: "{dup[1]}"')

            dup_url = _check_duplicate_url(conn, row.application_url)
            if dup_url and dup_url != sid:
                report.add_flag(sid, 'DUPLICATE_URL',
                                 f'Same URL as ID {dup_url}', severity='ERROR')

            ok, msg = _validate_url_quality(row.application_url)
            if not ok:
                report.add_flag(sid, 'GENERIC_URL', msg)

            source_count = conn.execute(
                text('SELECT COUNT(*) FROM scholarship_sources WHERE scholarship_id = :sid'),
                {'sid': sid},
            ).scalar() or 0
            if source_count == 0:
                report.add_flag(sid, 'NO_SOURCES',
                                 'No sources collected — URL may be invalid', severity='ERROR')

            criteria_count = conn.execute(
                text('SELECT COUNT(*) FROM eligibility_criteria WHERE scholarship_id = :sid'),
                {'sid': sid},
            ).scalar() or 0
            if criteria_count < 4:
                report.add_flag(sid, 'FEW_CRITERIA',
                                 f'Only {criteria_count} criteria (expected 5-8)')

            types = {
                row[0] for row in conn.execute(
                    text('SELECT DISTINCT criteria_type FROM eligibility_criteria WHERE scholarship_id = :sid'),
                    {'sid': sid},
                ).fetchall()
            }
            missing = {'demographic', 'academic_level'} - types
            if missing:
                report.add_flag(sid, 'MISSING_CRITERIA',
                                 f'Missing: {", ".join(sorted(missing))}')

    return report


# ── Pipeline orchestration ────────────────────────────────────────────────────

def run_pipeline(
    prompt_path: str,
    dry_run: bool = False,
    provided_ids: list[int] = None,
    batch_size: int = 10,
    batch_total: int = 5,
) -> ImportReport:
    """Full pipeline: discover → collect sources → normalize → validate."""
    tools_dir   = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(tools_dir)

    print('=' * 80)
    print('SCHOLARSHIP IMPORT PIPELINE')
    print(f'Started: {datetime.now():%Y-%m-%d %H:%M:%S}')
    if dry_run:
        print('DRY RUN — no changes will be made')
    print('=' * 80)

    # Step 1: Discover or use provided IDs
    if provided_ids:
        new_ids = provided_ids
        print(f'\nStep 1/4: Using {len(new_ids)} provided IDs: {new_ids}')
    elif dry_run:
        print('\nStep 1/4: DRY RUN — would run Serper discovery')
        new_ids = []
    else:
        print(f'\nStep 1/4: Discovering scholarships via Serper '
              f'({batch_total} queries × {batch_size} results) ...')
        new_ids = do_discover(prompt_path, batch_size=batch_size, batch_total=batch_total)
        if not new_ids:
            print('No new scholarships discovered.')
            return ImportReport()
        print(f'Discovered {len(new_ids)} new scholarships: {new_ids}')

    # Step 2: Collect sources
    if dry_run:
        print(f'\nStep 2/4: DRY RUN — would collect sources for {new_ids}')
    else:
        print(f'\nStep 2/4: Collecting sources for {len(new_ids)} scholarships ...')
        try:
            subprocess.run(
                [sys.executable, os.path.join(tools_dir, 'source_collector.py'),
                 '--ids', ','.join(map(str, new_ids))],
                cwd=project_dir, check=True,
            )
        except subprocess.CalledProcessError:
            logging.warning('source_collector.py had errors — continuing')

    # Step 3: Normalize criteria from sources
    if dry_run:
        print(f'\nStep 3/4: DRY RUN — would normalize criteria for {new_ids}')
    else:
        print('\nStep 3/4: Normalizing eligibility criteria ...')
        try:
            subprocess.run(
                [sys.executable, os.path.join(project_dir, 'normalize_from_sources.py'),
                 '--ids', ','.join(map(str, new_ids)), '--replace'],
                cwd=project_dir, check=True,
            )
        except subprocess.CalledProcessError:
            logging.warning('normalize_from_sources.py had errors — continuing')

    # Step 4: Validate and report
    if dry_run:
        print('\nStep 4/4: DRY RUN — would validate imported scholarships')
        return ImportReport()

    print(f'\nStep 4/4: Validating {len(new_ids)} scholarships ...')
    report = validate_imported(new_ids)
    report.print_summary()

    report_path = os.path.join(
        project_dir,
        f'import_report_{datetime.now():%Y%m%d_%H%M%S}.json',
    )
    with open(report_path, 'w', encoding='utf-8') as fh:
        json.dump(report.to_dict(), fh, indent=2)
    print(f'Report saved to: {report_path}')

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_ids(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(',') if x.strip()]


def read_urls_file(path: str) -> list[str]:
    with open(path, 'r', encoding='utf-8') as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith('#')]


def main():
    default_prompt = os.getenv('EXTRACTION_PROMPT_FILE', 'perplexity_prompt.txt')

    parser = argparse.ArgumentParser(
        description='Scholarship import pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--prompt', default=default_prompt,
                        help=f'Extraction prompt file (default: {default_prompt})')

    sub = parser.add_subparsers(dest='command', required=True)

    # discover
    p_discover = sub.add_parser('discover',
                                help='Find scholarship URLs via Serper, extract with Claude')
    p_discover.add_argument('--batches',   type=int, default=5,
                            help='Number of Serper queries to run (default: 5)')
    p_discover.add_argument('--per-batch', type=int, default=10,
                            help='Results per query (default: 10)')

    # from-urls
    p_urls = sub.add_parser('from-urls', help='Scrape from a URL list file')
    p_urls.add_argument('urls_file')
    p_urls.add_argument('--no-insert', action='store_true',
                        help='Extract but do not insert into DB')

    # rescrape
    p_rescrape = sub.add_parser('rescrape',
                                help='Re-scrape eligibility for existing records')
    p_rescrape.add_argument('--ids',     help='Comma-separated scholarship IDs')
    p_rescrape.add_argument('--limit',   type=int,
                            help='Max scholarships to process')
    p_rescrape.add_argument('--sleep',   type=float, default=0.5,
                            help='Seconds between API calls (default: 0.5)')
    p_rescrape.add_argument('--dry-run', action='store_true',
                            help='Show what would change without writing to DB')
    p_rescrape.add_argument('--all',     action='store_true',
                            help='Include scholarships that already have 5+ criteria')
    p_rescrape.add_argument('--free',    action='store_true',
                            help='Use rule-based BS4 extraction only — no Claude API calls')

    # run (full pipeline)
    p_run = sub.add_parser('run',
                           help='Full pipeline: discover → sources → normalize → validate')
    p_run.add_argument('--ids',       help='Skip discovery and process these IDs')
    p_run.add_argument('--dry-run',   action='store_true')
    p_run.add_argument('--batches',   type=int, default=5)
    p_run.add_argument('--per-batch', type=int, default=10)

    args = parser.parse_args()

    if not HAS_HTTPX:
        print('WARNING: httpx not installed — using urllib fallback.')
        print('Install with: pip install httpx beautifulsoup4 lxml anthropic')

    if args.command == 'discover':
        ids = do_discover(args.prompt, batch_size=args.per_batch, batch_total=args.batches)
        print(f'Done. Inserted IDs: {ids}')

    elif args.command == 'from-urls':
        urls = read_urls_file(args.urls_file)
        print(f'Processing {len(urls)} URLs ...')
        ids = do_from_urls(urls, args.prompt, insert=not args.no_insert)
        print(f'Done. Inserted IDs: {ids}')

    elif args.command == 'rescrape':
        do_rescrape(
            ids=parse_ids(args.ids),
            limit=args.limit,
            sleep=args.sleep,
            prompt_path=args.prompt,
            order_by_fewest=True,
            include_complete=args.all,
            dry_run=args.dry_run,
            use_claude=not args.free,
        )

    elif args.command == 'run':
        run_pipeline(
            prompt_path=args.prompt,
            dry_run=args.dry_run,
            provided_ids=parse_ids(args.ids) or None,
            batch_size=args.per_batch,
            batch_total=args.batches,
        )


if __name__ == '__main__':
    main()
