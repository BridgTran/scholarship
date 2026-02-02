import argparse
import json
import logging
import sys
import subprocess
import time
from urllib import request as urlrequest
import ssl

from dotenv import load_dotenv

from db import engine
from perplexity_import import (
    call_perplexity,
    extract_json,
    find_or_create_organization,
    insert_criteria,
    insert_scholarship,
    load_prompt,
    validate_scholarship,
)


def read_urls(path):
    urls = []
    with open(path, 'r', encoding='utf-8') as handle:
        for line in handle:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith('#'):
                urls.append(cleaned)
    return urls


def fetch_url(url, timeout_seconds=60, max_retries=2):
    user_agent = 'Mozilla/5.0 (compatible; ScholarshipBot/1.0)'
    curl_cmd = [
        'curl',
        '--location',
        '--silent',
        '--show-error',
        '--max-time',
        str(timeout_seconds),
        '--user-agent',
        user_agent,
        '--compressed',
        url
    ]
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                curl_cmd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.decode('utf-8', errors='ignore')
        except Exception:
            logging.exception('curl fetch failed for %s', url)

        req = urlrequest.Request(url, headers={'User-Agent': user_agent})
        try:
            with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except ssl.SSLError:
            context = ssl.create_default_context()
            if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
                context.options |= ssl.OP_LEGACY_SERVER_CONNECT
            with urlrequest.urlopen(
                req,
                context=context,
                timeout=timeout_seconds
            ) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception:
            logging.exception('Fetch failed for %s (attempt %s)', url, attempt + 1)
        time.sleep(1.5 * (attempt + 1))


def build_prompt(base_prompt, url, content):
    trimmed = content[:8000]
    return (
        f"{base_prompt}\n\n"
        f"Source URL: {url}\n"
        "Extract scholarship data from the page content below and return JSON only.\n"
        "Page content:\n"
        f"{trimmed}"
    )


def build_url_prompt(base_prompt, url):
    return (
        f"{base_prompt}\n\n"
        f"Source URL: {url}\n"
        "Fetch the page content yourself and extract scholarship data. "
        "Return JSON only."
    )


def scrape_urls(urls, prompt_path):
    base_prompt = load_prompt(prompt_path)
    scraped = []
    for url in urls:
        prompt = None
        try:
            content = fetch_url(url)
            if content:
                prompt = build_prompt(base_prompt, url, content)
        except Exception as exc:
            logging.exception("Failed to fetch URL: %s error=%s", url, exc)
        if prompt is None:
            prompt = build_url_prompt(base_prompt, url)
        try:
            response, raw_content = call_perplexity(prompt)
            data = response if isinstance(response, dict) else extract_json(raw_content)
            data['source_url'] = url
            scraped.append(data)
        except Exception as exc:
            logging.exception("Failed to parse Perplexity response for %s error=%s", url, exc)
    return scraped


def insert_scraped(scraped):
    inserted = 0
    skipped = 0
    skipped_invalid = 0
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for entry in scraped:
                scholarships = entry.get('scholarships', [])
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
                            insert_criteria(
                                conn,
                                scholarship_id,
                                criteria,
                                source_url=scholarship.get('application_url')
                            )
                    inserted += 1
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    return inserted, skipped, skipped_invalid


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Scrape scholarship URLs with Perplexity.')
    parser.add_argument('--urls-file', required=True, help='Path to text file with URLs.')
    parser.add_argument('--prompt', default='perplexity_prompt.txt', help='Prompt file path.')
    parser.add_argument('--output', default='scraped_scholarships.json', help='Output JSON path.')
    parser.add_argument('--insert', action='store_true', help='Insert results into DB.')
    args = parser.parse_args()

    urls = read_urls(args.urls_file)
    if not urls:
        print('No URLs provided.')
        return 1

    scraped = scrape_urls(urls, args.prompt)
    with open(args.output, 'w', encoding='utf-8') as handle:
        json.dump(scraped, handle, ensure_ascii=True, indent=2)
    print(f'Saved {len(scraped)} entries to {args.output}')

    if args.insert:
        inserted, skipped, skipped_invalid = insert_scraped(scraped)
        print(
            f'Inserted {inserted} scholarships. '
            f'Skipped {skipped} duplicates. '
            f'Skipped {skipped_invalid} invalid.'
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
