#!/usr/bin/env python3
"""Preview extraction results for a list of URLs without inserting."""
import json, sys, time, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.WARNING)

from tools.import_pipeline import fetch_url, extract_scholarship_bs4, confidence_score, \
    extract_main_text, call_claude, CONFIDENCE_THRESHOLD

PROMPT_PATH = 'perplexity_prompt.txt'

urls = [
    'https://www.nswtf.org.au/news/2026/02/04/applications-now-open-for-federations-4000-future-teacher-scholarships/',
    'https://www.nswnma.asn.au/education/scholarships/',
    'https://www.nsw.gov.au/housing-and-construction/social-affordable/public-housing-tenants/jobseekers-and-students/youth-development-scholarships',
    'https://www.swinburne.edu.au/study/options/scholarships/421/freemasons-foundation-victoria-scholarship-2026/',
    'https://www.swinburne.edu.au/study/options/scholarships/550/david-johnson-freemasons-foundation-scholarship-2026/',
    'https://www.acu.edu.au/study-at-acu/fees-and-scholarships/find-a-scholarship/freemasons-foundation-scholarship',
    'https://cef.org.au/search-for-scholarships/',
    'https://americanaustralian.org/scholarships/',
]

results = []
for url in urls:
    print(f'\n{"="*70}')
    print(f'URL: {url}')
    try:
        html = fetch_url(url)
    except Exception as e:
        print(f'  FETCH FAILED: {e}')
        continue
    data  = extract_scholarship_bs4(html, url)
    score = confidence_score(data)
    if score >= CONFIDENCE_THRESHOLD:
        scholarships = [data]
        method = f'heuristic (score={score:.2f})'
    else:
        try:
            text = extract_main_text(html)
            resp = call_claude(text, url, PROMPT_PATH)
            scholarships = resp.get('scholarships', [])
            method = f'claude (heuristic score={score:.2f})'
        except Exception as e:
            print(f'  CLAUDE FAILED: {e}')
            continue
    print(f'  Method: {method}')
    print(f'  Scholarships found: {len(scholarships)}')
    for i, s in enumerate(scholarships, 1):
        print(f'\n  [{i}] {s.get("title","(no title)")}')
        print(f'      amount:    {s.get("amount")}')
        print(f'      deadline:  {s.get("deadline")}')
        print(f'      status:    {s.get("status")}')
        print(f'      type:      {s.get("scholarship_type")}')
        print(f'      org:       {(s.get("organization") or {}).get("name")}')
        print(f'      industry:  {s.get("industry")}')
        print(f'      app_url:   {s.get("application_url")}')
        print(f'      criteria:  {len(s.get("eligibility_criteria") or [])} items')
        print(f'      desc:      {(s.get("description") or "")[:120]}')
    results.extend(scholarships)
    time.sleep(0.5)

print(f'\n{"="*70}')
print(f'TOTAL SCHOLARSHIPS EXTRACTED: {len(results)}')
