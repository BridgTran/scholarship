import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from sqlalchemy import text, bindparam

from db import engine


KEYWORDS = [
    'terms',
    'condition',
    'policy',
    'guidelines',
    'rules',
    'eligibility',
    'how to apply',
    'faq',
    'download'
]


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._current_href = None
        self._current_text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self._skip = True
        if tag != 'a':
            return
        href = None
        for key, value in attrs:
            if key == 'href':
                href = value
                break
        self._current_href = href
        self._current_text = []

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self._skip = False
        if tag != 'a':
            return
        text = ''.join(self._current_text).strip()
        self.links.append((self._current_href, text))
        self._current_href = None
        self._current_text = []

    def handle_data(self, data):
        if self._skip:
            return
        if self._current_href is not None:
            self._current_text.append(data)


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = False
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'noscript'}:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}:
            self._skip = False

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self):
        return '\n'.join(self._chunks)


def sha256_bytes(payload):
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def fetch_url(url, timeout=20):
    req = Request(url, headers={'User-Agent': 'ScholarshipBot/1.0'})
    with urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
        data = resp.read()
    return content_type, data


def extract_main_text(html_bytes):
    html = html_bytes.decode('utf-8', errors='ignore')
    html = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\\1>', ' ', html)
    html = re.sub(r'(?is)<(header|footer|nav|aside)[^>]*>.*?</\\1>', ' ', html)
    html = re.sub(
        r'(?is)<(section|div|ul|nav)[^>]*(id|class)=[\'"][^\'"]*quick[^\'"]*link[^\'"]*[\'"][^>]*>.*?</\\1>',
        ' ',
        html
    )

    candidates = [
        r'(?is)<main[^>]*>.*?</main>',
        r'(?is)<article[^>]*>.*?</article>',
        r'(?is)<section[^>]*(id|class)=[\'"][^\'"]*(content|main|article|body|primary|page)[^\'"]*[\'"][^>]*>.*?</section>',
        r'(?is)<div[^>]*(id|class)=[\'"][^\'"]*(content|main|article|body|primary|page)[^\'"]*[\'"][^>]*>.*?</div>',
    ]
    main_html = ''
    for pattern in candidates:
        match = re.search(pattern, html)
        if match:
            main_html = match.group(0)
            break

    if not main_html:
        return ''

    parser = TextExtractor()
    parser.feed(main_html)
    text = parser.get_text()

    boilerplate_patterns = [
        re.compile(r'\bquick links?\b', re.IGNORECASE),
        re.compile(r'\bcricos\b', re.IGNORECASE),
        re.compile(r'\bteqsa\b', re.IGNORECASE),
    ]
    seen = set()
    cleaned_lines = []
    for line in text.splitlines():
        normalized = ' '.join(line.split())
        if not normalized:
            continue
        if any(pattern.search(normalized) for pattern in boilerplate_patterns):
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_lines.append(normalized)
    return '\n'.join(cleaned_lines)


def extract_links(html_bytes):
    parser = LinkCollector()
    parser.feed(html_bytes.decode('utf-8', errors='ignore'))
    return parser.links


def is_allowed_domain(url, base_domain, allowlist):
    hostname = urlparse(url).hostname or ''
    if not hostname:
        return False
    if hostname == base_domain or hostname.endswith(f".{base_domain}"):
        return True
    if hostname.endswith('.edu.au') or hostname.endswith('.gov.au'):
        return True
    for domain in allowlist:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return True
    return False


def is_related_link(href, text):
    if not href:
        return False
    href_lower = href.lower()
    text_lower = (text or '').lower()
    if href_lower.endswith('.pdf'):
        return True
    for keyword in KEYWORDS:
        if keyword in href_lower or keyword in text_lower:
            return True
    return False


def extract_pdf_text(pdf_bytes):
    pdftotext = shutil.which('pdftotext')
    if not pdftotext:
        return ''
    with tempfile.NamedTemporaryFile(suffix='.pdf') as pdf_file:
        pdf_file.write(pdf_bytes)
        pdf_file.flush()
        with tempfile.NamedTemporaryFile(suffix='.txt') as text_file:
            subprocess.run(
                [pdftotext, pdf_file.name, text_file.name],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            text_file.seek(0)
            return text_file.read().decode('utf-8', errors='ignore').strip()


def ensure_sources_table(conn):
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS scholarship_sources (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scholarship_id INT NOT NULL,
            url VARCHAR(2048) NOT NULL,
            content_type VARCHAR(20) NOT NULL,
            fetched_at DATETIME NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            raw_text LONGTEXT NULL,
            raw_bytes_path VARCHAR(512) NULL,
            INDEX idx_scholarship_id (scholarship_id),
            INDEX idx_url (url)
        )
    '''))


def parse_id_list(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(',') if item.strip()]


def insert_source(payload):
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO scholarship_sources
            (scholarship_id, url, content_type, fetched_at, content_hash, raw_text, raw_bytes_path)
            VALUES
            (:scholarship_id, :url, :content_type, :fetched_at, :content_hash, :raw_text, :raw_bytes_path)
        '''), payload)


def main():
    parser = argparse.ArgumentParser(description='Collect scholarship sources.')
    parser.add_argument('--ids', help='Comma-separated scholarship IDs to process.')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--max-sources', type=int, default=10)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()

    allowlist = [
        domain.strip()
        for domain in os.getenv('ALLOWED_SOURCE_DOMAINS', '').split(',')
        if domain.strip()
    ]

    base_query = '''
        SELECT id, application_url
        FROM scholarships
        WHERE application_url IS NOT NULL
        AND application_url != ''
    '''

    ids = parse_id_list(args.ids)
    parsed_ids = []
    if ids:
        for item in ids:
            try:
                parsed_ids.append(int(item))
            except ValueError:
                raise SystemExit(f"Invalid scholarship id: {item}")

    with engine.begin() as conn:
        ensure_sources_table(conn)

    if parsed_ids:
        stmt = text('''
            SELECT id, application_url
            FROM scholarships
            WHERE id IN :ids
        ''').bindparams(bindparam('ids', expanding=True))
        with engine.connect() as conn:
            scholarships = conn.execute(stmt, {'ids': parsed_ids}).fetchall()
    else:
        with engine.connect() as conn:
            scholarships = conn.execute(text(base_query)).fetchall()

    if args.limit and not parsed_ids:
        scholarships = scholarships[:args.limit]

    found_ids = {row.id for row in scholarships}
    missing_ids = [item for item in parsed_ids if item not in found_ids]
    if missing_ids:
        print(f"Missing scholarships for ids: {', '.join(str(item) for item in missing_ids)}")

    print(f"Selected {len(scholarships)} scholarships.")

    sources_dir = os.path.join(os.getcwd(), 'scholarship_sources')
    os.makedirs(sources_dir, exist_ok=True)

    for scholarship in scholarships:
        stored_count = 0
        main_url = scholarship.application_url
        print(f"Processing scholarship {scholarship.id}: {main_url}")
        if not main_url:
            print(f"Scholarship {scholarship.id} has no application_url.")
            print(f"stored {stored_count} sources")
            continue

        with engine.connect() as conn:
            existing_count = conn.execute(text('''
                SELECT COUNT(*) FROM scholarship_sources WHERE scholarship_id = :scholarship_id
            '''), {'scholarship_id': scholarship.id}).scalar() or 0
        if existing_count > 0 and not args.refresh:
            print(f"Skipping scholarship {scholarship.id}: {existing_count} sources already exist.")
            print(f"stored {stored_count} sources")
            continue

        base_domain = urlparse(main_url).hostname or ''
        if not base_domain:
            print(f"Invalid application_url for scholarship {scholarship.id}: {main_url}")
            print(f"stored {stored_count} sources")
            continue

        try:
            content_type, data = fetch_url(main_url)
        except Exception as exc:
            print(f"Failed to fetch {main_url}: {exc}")
            print(f"stored {stored_count} sources")
            continue

        content_hash = sha256_bytes(data)
        raw_text = ''
        if content_type == 'text/html' or main_url.lower().endswith('.html'):
            raw_text = extract_main_text(data)

        insert_source({
            'scholarship_id': scholarship.id,
            'url': main_url,
            'content_type': 'html' if content_type == 'text/html' else content_type,
            'fetched_at': datetime.utcnow(),
            'content_hash': content_hash,
            'raw_text': raw_text,
            'raw_bytes_path': None
        })
        stored_count += 1

        if content_type != 'text/html':
            print(f"stored {stored_count} sources")
            continue

        links = extract_links(data)
        related_urls = []
        for href, anchor_text in links:
            if not href:
                continue
            normalized = urljoin(main_url, href)
            if not is_related_link(href, anchor_text):
                continue
            if not is_allowed_domain(normalized, base_domain, allowlist):
                continue
            if normalized in related_urls or normalized == main_url:
                continue
            related_urls.append(normalized)
            if len(related_urls) >= max(args.max_sources - 1, 0):
                break

        for related_url in related_urls:
            try:
                related_type, related_data = fetch_url(related_url)
            except Exception as exc:
                print(f"Failed to fetch {related_url}: {exc}")
                continue
            related_hash = sha256_bytes(related_data)

            raw_text = ''
            raw_bytes_path = None
            content_kind = 'html' if related_type == 'text/html' else related_type

            if related_url.lower().endswith('.pdf') or related_type == 'application/pdf':
                filename = f"{scholarship.id}_{related_hash}.pdf"
                raw_bytes_path = os.path.join(sources_dir, filename)
                with open(raw_bytes_path, 'wb') as handle:
                    handle.write(related_data)
                raw_text = extract_pdf_text(related_data)
                content_kind = 'pdf'
            elif content_kind == 'html':
                raw_text = extract_main_text(related_data)

            insert_source({
                'scholarship_id': scholarship.id,
                'url': related_url,
                'content_type': content_kind,
                'fetched_at': datetime.utcnow(),
                'content_hash': related_hash,
                'raw_text': raw_text,
                'raw_bytes_path': raw_bytes_path
            })
            stored_count += 1

        print(f"stored {stored_count} sources")


if __name__ == '__main__':
    main()
