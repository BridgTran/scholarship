#!/usr/bin/env python3
"""
Source Collector

Fetches the application URL for each scholarship, extracts related links
(PDFs, terms pages, eligibility docs), and stores raw text in scholarship_sources.

Usage:
    python tools/source_collector.py --ids 147,148
    python tools/source_collector.py               # process all scholarships
    python tools/source_collector.py --refresh     # re-fetch already-stored sources
    python tools/source_collector.py --limit 10
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from urllib.parse import urljoin, urlparse

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

from sqlalchemy import text, bindparam
from db import engine


# ── Constants ─────────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-AU,en;q=0.9',
}

RELATED_KEYWORDS = [
    'terms', 'condition', 'policy', 'guidelines', 'rules',
    'eligibility', 'how to apply', 'faq', 'download',
]

BOILERPLATE_RE = [
    re.compile(r'\bquick links?\b', re.IGNORECASE),
    re.compile(r'\bcricos\b',       re.IGNORECASE),
    re.compile(r'\bteqsa\b',        re.IGNORECASE),
]

SKIP_TAGS = {'script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside'}

CONTENT_ATTRS = re.compile(
    r'content|main|article|body|primary|page|scholarship|eligib',
    re.IGNORECASE,
)


# ── Fetching ──────────────────────────────────────────────────────────────────

def sha256_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_url(url: str, timeout: int = 20) -> tuple[str, bytes]:
    """Return (content_type, raw_bytes). Raises on HTTP error."""
    if HAS_HTTPX:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get('content-type', '').split(';')[0].strip().lower()
            return ct, resp.content

    # urllib fallback
    from urllib.request import Request, urlopen
    req = Request(url, headers={'User-Agent': HEADERS['User-Agent']})
    with urlopen(req, timeout=timeout) as resp:
        ct = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
        return ct, resp.read()


def _find_content_element(soup):
    """Return the best main-content container in the page."""
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


def extract_links(html_bytes: bytes, base_url: str) -> list[tuple[str, str]]:
    """Return list of (absolute_url, anchor_text) from HTML."""
    if HAS_BS4:
        soup = BeautifulSoup(html_bytes, 'lxml')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('javascript:', 'mailto:', '#')):
                continue
            links.append((urljoin(base_url, href), a.get_text(strip=True)))
        return links

    # Minimal HTMLParser fallback
    from html.parser import HTMLParser

    class _Collector(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []
            self._href = None
            self._text: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self._href = next((v for k, v in attrs if k == 'href'), None)
                self._text = []

        def handle_endtag(self, tag):
            if tag == 'a' and self._href:
                self.links.append((urljoin(base_url, self._href), ''.join(self._text).strip()))
                self._href = None

        def handle_data(self, data):
            if self._href is not None:
                self._text.append(data)

    p = _Collector()
    p.feed(html_bytes.decode('utf-8', errors='ignore'))
    return p.links


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdftotext (if available)."""
    pdftotext = shutil.which('pdftotext')
    if not pdftotext:
        return ''
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fh:
        fh.write(pdf_bytes)
        pdf_path = fh.name
    txt_path = pdf_path.replace('.pdf', '.txt')
    try:
        subprocess.run(
            [pdftotext, pdf_path, txt_path],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as fh:
                return fh.read().strip()
    finally:
        for path in [pdf_path, txt_path]:
            if os.path.exists(path):
                os.unlink(path)
    return ''


def is_allowed_domain(url: str, base_domain: str, allowlist: list[str]) -> bool:
    hostname = urlparse(url).hostname or ''
    if not hostname:
        return False
    if hostname == base_domain or hostname.endswith(f'.{base_domain}'):
        return True
    if hostname.endswith('.edu.au') or hostname.endswith('.gov.au'):
        return True
    return any(hostname == d or hostname.endswith(f'.{d}') for d in allowlist)


def is_related_link(href: str, anchor_text: str) -> bool:
    if not href:
        return False
    if href.lower().endswith('.pdf'):
        return True
    combined = (href + ' ' + (anchor_text or '')).lower()
    return any(kw in combined for kw in RELATED_KEYWORDS)


# ── DB ─────────────────────────────────────────────────────────────────────────

def ensure_sources_table(conn):
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS scholarship_sources (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            scholarship_id  INT NOT NULL,
            url             VARCHAR(2048) NOT NULL,
            content_type    VARCHAR(20)   NOT NULL,
            fetched_at      DATETIME      NOT NULL,
            content_hash    VARCHAR(64)   NOT NULL,
            raw_text        LONGTEXT      NULL,
            raw_bytes_path  VARCHAR(512)  NULL,
            INDEX idx_scholarship_id (scholarship_id),
            INDEX idx_url (url(255))
        )
    '''))


def insert_source(scholarship_id: int, url: str, content_type: str,
                  raw_text: str, raw_bytes_path: str | None, content_hash: str):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO scholarship_sources
            (scholarship_id, url, content_type, fetched_at, content_hash, raw_text, raw_bytes_path)
            VALUES
            (:scholarship_id, :url, :content_type, :fetched_at, :content_hash, :raw_text, :raw_bytes_path)
        '''), {
            'scholarship_id': scholarship_id,
            'url':            url,
            'content_type':   content_type,
            'fetched_at':     datetime.utcnow(),
            'content_hash':   content_hash,
            'raw_text':       raw_text,
            'raw_bytes_path': raw_bytes_path,
        })


# ── Main collection logic ──────────────────────────────────────────────────────

def collect_sources_for(scholarship_id: int, main_url: str,
                        sources_dir: str, max_sources: int = 10,
                        allowlist: list[str] = None) -> int:
    """Fetch and store sources for one scholarship. Returns count stored."""
    allowlist   = allowlist or []
    base_domain = urlparse(main_url).hostname or ''
    stored      = 0

    try:
        content_type, data = fetch_url(main_url)
    except Exception as exc:
        print(f'  Failed to fetch {main_url}: {exc}')
        return 0

    content_hash = sha256_of(data)
    is_html      = 'html' in content_type
    raw_text     = extract_main_text(data) if is_html else ''
    insert_source(scholarship_id, main_url,
                  'html' if is_html else content_type,
                  raw_text, None, content_hash)
    stored += 1

    if not is_html:
        return stored

    related_urls: list[str] = []
    for href, anchor in extract_links(data, main_url):
        if not is_related_link(href, anchor):
            continue
        if not is_allowed_domain(href, base_domain, allowlist):
            continue
        if href in related_urls or href == main_url:
            continue
        related_urls.append(href)
        if len(related_urls) >= max_sources - 1:
            break

    for rel_url in related_urls:
        try:
            rel_type, rel_data = fetch_url(rel_url)
        except Exception as exc:
            print(f'  Failed to fetch {rel_url}: {exc}')
            continue

        rel_hash = sha256_of(rel_data)
        rel_text = ''
        rel_path = None
        rel_kind = 'html' if 'html' in rel_type else rel_type

        if rel_url.lower().endswith('.pdf') or 'pdf' in rel_type:
            filename = f'{scholarship_id}_{rel_hash}.pdf'
            rel_path = os.path.join(sources_dir, filename)
            with open(rel_path, 'wb') as fh:
                fh.write(rel_data)
            rel_text = extract_pdf_text(rel_data)
            rel_kind = 'pdf'
        elif 'html' in rel_type:
            rel_text = extract_main_text(rel_data)

        insert_source(scholarship_id, rel_url, rel_kind, rel_text, rel_path, rel_hash)
        stored += 1

    return stored


def main():
    parser = argparse.ArgumentParser(description='Collect scholarship source pages.')
    parser.add_argument('--ids',         help='Comma-separated scholarship IDs')
    parser.add_argument('--limit',       type=int, default=None)
    parser.add_argument('--max-sources', type=int, default=10)
    parser.add_argument('--refresh',     action='store_true',
                        help='Re-fetch even if sources already exist')
    args = parser.parse_args()

    if not HAS_HTTPX:
        print('WARNING: httpx not installed — falling back to urllib.')
        print('Install with: pip install httpx beautifulsoup4 lxml')

    allowlist = [
        d.strip()
        for d in os.getenv('ALLOWED_SOURCE_DOMAINS', '').split(',')
        if d.strip()
    ]

    with engine.begin() as conn:
        ensure_sources_table(conn)

    parsed_ids = []
    if args.ids:
        parsed_ids = [int(x) for x in args.ids.split(',') if x.strip()]

    with engine.connect() as conn:
        if parsed_ids:
            stmt = text('SELECT id, application_url FROM scholarships WHERE id IN :ids') \
                .bindparams(bindparam('ids', expanding=True))
            scholarships = conn.execute(stmt, {'ids': parsed_ids}).fetchall()
        else:
            scholarships = conn.execute(text('''
                SELECT id, application_url FROM scholarships
                WHERE application_url IS NOT NULL AND application_url != ''
            ''')).fetchall()

    if args.limit and not parsed_ids:
        scholarships = scholarships[:args.limit]

    found_ids   = {row.id for row in scholarships}
    missing_ids = [i for i in parsed_ids if i not in found_ids]
    if missing_ids:
        print(f'Warning: no scholarships found for IDs {missing_ids}')

    print(f'Processing {len(scholarships)} scholarships ...')
    sources_dir = os.path.join(os.getcwd(), 'scholarship_sources')
    os.makedirs(sources_dir, exist_ok=True)

    for row in scholarships:
        if not row.application_url:
            print(f'  [{row.id}] No application_url — skipping')
            continue

        if not args.refresh:
            with engine.connect() as conn:
                count = conn.execute(
                    text('SELECT COUNT(*) FROM scholarship_sources WHERE scholarship_id = :sid'),
                    {'sid': row.id},
                ).scalar() or 0
            if count > 0:
                print(f'  [{row.id}] Already has {count} sources — skipping (use --refresh to re-fetch)')
                continue

        print(f'  [{row.id}] {row.application_url}')
        stored = collect_sources_for(
            row.id, row.application_url, sources_dir,
            max_sources=args.max_sources, allowlist=allowlist,
        )
        print(f'  [{row.id}] Stored {stored} sources')


if __name__ == '__main__':
    main()
