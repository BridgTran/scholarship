import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, bindparam

from db import engine
from criteria_utils import normalize_criteria_type, normalize_criteria_key, validate_criteria_key


CURRENT_SCHOLARSHIP_ID = None


PREFERRED_TERMS = [
    'preferred',
    'desirable',
    'advantage',
    'nice to have'
]

BOILERPLATE_LINE_PATTERNS = [
    r'\bteqsa\b',
    r'\bquick links?\b',
    r'\bemployer of choice\b',
    r'\bcricos provider\b',
    # Contact / navigation chrome
    r'^\s*contact\s+us\s*$',
    r'^\s*make\s+an\s+enquiry\s*$',
    r'^\s*apply\s+now\s*$',
    r'^\s*read\s+the\s+faqs?\s*$',
    r'^\s*frequently\s+asked\s+questions?\s*$',
    r'\bprospective\s+students?\b',
    r'\bcurrent\s+students?\b',
    # Business hours / phone boilerplate
    r'open\s+\d+\s*am\b',
    r'^\s*\+?[\d\s\-\(\)\.]{7,}\s*$',   # bare phone number line
    r'^\s*1800\s+[a-z\s]+\s*$',          # 1800 vanity numbers
]

# ── Junk filter for fallback exclusion rows ───────────────────────────────────

_PHONE_RE = re.compile(r'^\+?[\d\s\-\(\)\.]{7,}$')

_JUNK_EXCLUSION_RE = [re.compile(p, re.IGNORECASE) for p in [
    r'^\s*contact\s+us\s*$',
    r'^\s*make\s+an\s+enquiry\s*$',
    r'^\s*apply\s+now\s*$',
    r'^\s*read\s+the\s+faqs?\s*$',
    r'^\s*frequently\s+asked\s+questions?\s*$',
    r'\bprospective\s+students?\s*(\(domestic\)|\(international\))?\s*$',
    r'^\s*current\s+students?\s*$',
    r'open\s+\d+\s*am\b',
    r'^\s*1800\s+[a-z\s]+\s*$',
    r'^\s*phone\s*:?\s*$',
    r'^\s*[IVX]+\.\s*$',              # lone roman numeral (II., III.)
    r'^\s*[\(\)]\s*$',                # lone bracket
]]


def _is_junk_exclusion(line: str) -> bool:
    """Return True if this line is too trivial to be a meaningful exclusion criterion."""
    stripped = line.strip()
    if len(stripped) < 10:            # catches "(", "N/A", "Phone", "UTS", "II."
        return True
    if _PHONE_RE.match(stripped):
        return True
    return any(p.search(stripped) for p in _JUNK_EXCLUSION_RE)

REQUIRED_TERMS = [
    'must',
    'not eligible',
    'are not eligible if',
    'must not be',
    'ineligible'
]

INCLUSION_TERMS = [
    'is eligible if',
    'are eligible if',
    'you are eligible if',
    'applicants are eligible if',
    'students are eligible if',
    'eligible if',
    'to be eligible',
    'to be eligible, you must',
    'to be eligible you must',
    'to be eligible applicants must',
    'must',
    'must be',
    'must have',
    'must meet',
    'must satisfy',
    'required to',
    'is required to',
    'are required to',
    'eligibility criteria',
    'eligibility requirements',
    'selection criteria',
    'open to',
    'available to',
    'is available to',
    'applications are open to',
    'this scholarship is open to',
    'applicants must',
    'candidates must',
    'eligibility',
    'you must',
    'this scholarship is available to'
]

EXCLUSION_TERMS = [
    'are not eligible if',
    'is not eligible if',
    'you are not eligible if',
    'applicants are not eligible if',
    'students are not eligible if',
    'will not be eligible if',
    'not eligible if',
    'ineligible if',
    'is ineligible if',
    'are ineligible if',
    'are not eligible to apply if',
    'is not eligible to apply if',
    'not eligible to apply',
    'ineligible to apply',
    'will not be considered if',
    'will not be considered',
    'will not be accepted if',
    'applications will not be accepted if',
    'applications will not be considered if',
    'must not',
    'must not be',
    'cannot be',
    'may not be eligible if',
    'may be ineligible if',
    'excluding',
    'excluded',
    'are excluded if',
    'is excluded if',
    'is excluded',
    'are excluded',
    'does not apply to',
    'this scholarship is not available to',
    'not available to',
    'not open to',
    'not offered to',
    'not intended for',
    'is not for',
    'is not applicable to',
    'will be disqualified if',
    'may be disqualified if',
    'disqualified if',
    'grounds for disqualification',
    'will be deemed ineligible if',
    'deemed ineligible if',
    'no longer eligible if',
    'ceases to be eligible if',
    'except',
    'excluded',
    'excluding',
    'ineligible',
    'ineligible for',
    'not eligible',
    'not eligible for',
    'not eligible to',
    'not open to',
    'not available to',
    'not available for',
    'does not apply to',
    'does not apply for',
    'not offered to',
    'not intended for',
    'not for',
    'no longer eligible',
    'will not be considered',
    'not considered',
    'cannot apply',
    'may not apply',
    'not permitted',
    'not supported',
    'not applicable to',
    'not applicable for',
    'not eligible unless'
]

OVERRIDE_TERMS = [
    'exception',
    'exceptions',
    'override',
    'overrides',
    'unless',
    'except for',
    'except',
    'with the exception of',
    'provided that',
    'only if',
    'notwithstanding',
    'despite',
    'however'
]

COMMON_HEADINGS = [
    'how to apply',
    'contact',
    'eligibility',
    'selection criteria',
    'faq',
    'prepare to apply',
    'exceptions',
    'future study',
    'how to accept',
    'how to accept a university funded scholarship'
]

EXCLUSION_TRIGGERS = [
    'applicants are not eligible',
    'you are not eligible',
    'ineligible',
    'not eligible',
    'except for the following',
    'ineligible programs'
]

EXCLUSION_END_HEADINGS = [
    'benefits',
    'value',
    'how to apply',
    'how to accept',
    'to receive the scholarship',
    'conditions',
    'offer of admission',
    'confirmation of enrolment',
    'enrolment'
]

EXCLUSION_REASON_PATTERNS = [
    r'\bnot\b',
    r'\bcannot\b',
    r'\bmust not\b',
    r'\bineligible\b',
    r'\bexcluded\b',
    r'\bexcept\b',
    r'\bare a citizen\b',
    r'\bpermanent resident\b',
    r'\bexchange\b',
    r'\bstudy abroad\b',
    r'\bcurrently enrolled\b',
    r'\bdo not commence\b',
    r'\bdefer\b',
    r'\badvanced standing\b',
    r'\bcredit points?\b',
    r'\bcampus\b',
    r'\banother scholarship\b'
]

SECTION_ELIGIBLE = 'ELIGIBLE'
SECTION_EXCLUDED = 'EXCLUDED'
SECTION_BENEFITS = 'BENEFITS'
SECTION_CONDITIONS = 'CONDITIONS'
SECTION_OTHER = 'OTHER'

SECTION_TRIGGERS = {
    SECTION_ELIGIBLE: INCLUSION_TERMS,
    SECTION_EXCLUDED: EXCLUSION_TERMS + [
        'applicants are not eligible',
        'you are not eligible',
        'not eligible',
        'ineligible',
        'except for the following',
        'ineligible programs'
    ],
    SECTION_BENEFITS: [
        'value',
        'benefits',
        'what you receive',
        'tuition fee',
        '% tuition'
    ],
    SECTION_CONDITIONS: [
        'conditions',
        'to receive',
        'to keep',
        'ongoing',
        'must maintain',
        'payment will be',
        'confirmation of enrolment',
        'offer of admission',
        'commence study',
        'cannot be deferred'
    ]
}

STATE_CODES = ['NSW', 'ACT', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT']
BULLET_RE = re.compile(r'^\s*(?:[-•*]|\d+\.|[a-zA-Z]\.)\s+')
MAX_BULLETS_UNDER_ONE_TRIGGER = 12
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


def find_sentence(text, start, end):
    if not text:
        return ''
    boundary = max(
        text.rfind('.', 0, start),
        text.rfind(';', 0, start),
        text.rfind('\n', 0, start)
    )
    boundary = 0 if boundary == -1 else boundary + 1
    next_stop = min(
        [pos for pos in [
            text.find('.', end),
            text.find(';', end),
            text.find('\n', end)
        ] if pos != -1] or [len(text)]
    )
    return text[boundary:next_stop].strip()


def infer_is_required(sentence):
    sentence_lower = sentence.lower()
    if any(term in sentence_lower for term in PREFERRED_TERMS):
        return False
    if any(term in sentence_lower for term in REQUIRED_TERMS):
        return True
    return True


def is_exclusion_sentence(sentence):
    if not sentence:
        return False
    sentence_lower = sentence.lower()
    return any(term in sentence_lower for term in EXCLUSION_TERMS)


def excluded_criteria_key(criteria_key):
    if not criteria_key:
        return criteria_key
    if criteria_key.endswith('_excluded') or criteria_key.endswith('_exclusion'):
        return criteria_key
    return f"{criteria_key}_excluded"


def append_criteria(
    target,
    criteria_type,
    criteria_key,
    required_value,
    is_required,
    sentence=None,
    force_excluded=False,
    detect_exclusion=True
):
    if force_excluded or (detect_exclusion and is_exclusion_sentence(sentence)):
        excluded_key = excluded_criteria_key(criteria_key)
        print(f"INSERTED excluded row: {criteria_type} {excluded_key} {required_value}")
        target.append({
            'criteria_type': criteria_type,
            'criteria_key': excluded_key,
            'required_value': required_value,
            'is_required': True
        })
        return
    target.append({
        'criteria_type': criteria_type,
        'criteria_key': criteria_key,
        'required_value': required_value,
        'is_required': is_required
    })


def clean_source_text(text):
    if not text:
        return ''
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in BOILERPLATE_LINE_PATTERNS]
    seen = set()
    cleaned_lines = []
    for line in text.splitlines():
        normalized = ' '.join(line.split())
        if not normalized:
            continue
        if any(pattern.search(normalized) for pattern in patterns):
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_lines.append(normalized)
    return '\n'.join(cleaned_lines)


def apply_exclusion_context(text):
    exclusion_mode = False
    pending_blank = False
    updated_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            pending_blank = True
            continue
        lower_line = stripped.lower()
        if any(trigger in lower_line for trigger in EXCLUSION_TRIGGERS):
            exclusion_mode = True
            if CURRENT_SCHOLARSHIP_ID == 147:
                print(f"EXCLUSION MODE ON: {stripped}")
            pending_blank = False
            continue

        is_heading = any(lower_line.startswith(heading) for heading in EXCLUSION_END_HEADINGS)
        is_bullet = BULLET_RE.match(line) is not None
        has_reason_terms = any(re.search(pattern, lower_line) for pattern in EXCLUSION_REASON_PATTERNS)

        if exclusion_mode and is_bullet:
            if not has_reason_terms:
                exclusion_mode = False
                pending_blank = False
                updated_lines.append(stripped)
                continue
            cleaned = BULLET_RE.sub('', stripped).strip()
            updated_lines.append(f"Not eligible: {cleaned}")
            pending_blank = False
            continue

        if exclusion_mode:
            if pending_blank and is_heading:
                exclusion_mode = False
            elif is_heading:
                exclusion_mode = False
            elif pending_blank and not is_bullet:
                exclusion_mode = False
            pending_blank = False

        updated_lines.append(stripped)
    return '\n'.join(updated_lines)


def parse_exclusion_bullets(text):
    exclusion_mode = False
    lines_since_trigger = 0
    pending_blank = False
    student_ineligible_block = False
    excluded_bullets = []
    non_excluded_bullets = []
    student_ineligible_bullets = []
    lines = text.splitlines()
    line_count = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            pending_blank = True
            continue
        lower_line = stripped.lower()
        if has_exclusion_trigger(lower_line):
            if next_lines_contain_bullets(index, lines):
                exclusion_mode = True
                lines_since_trigger = 0
                student_ineligible_block = re.search(
                    r'\bstudents?\s+(are|is)\s+not\s+eligible\s+if\b',
                    lower_line
                ) is not None
                print(f"EXCLUSION MODE ON: {stripped}")
                pending_blank = False
            else:
                insert_exclusion_sentence(stripped, lower_line, excluded_bullets)
                exclusion_mode = False
            continue
        if any(lower_line.startswith(heading) for heading in EXCLUSION_END_HEADINGS):
            exclusion_mode = False
            student_ineligible_block = False
            pending_blank = False
        if not exclusion_mode:
            continue
        lines_since_trigger += 1
        if lines_since_trigger > MAX_BULLETS_UNDER_ONE_TRIGGER:
            exclusion_mode = False
            student_ineligible_block = False
            pending_blank = False
            continue
        is_bullet = BULLET_RE.match(line) is not None
        has_reason_terms = any(re.search(pattern, lower_line) for pattern in EXCLUSION_REASON_PATTERNS)
        if pending_blank and not is_bullet:
            exclusion_mode = False
            student_ineligible_block = False
            pending_blank = False
            continue
        if is_bullet:
            cleaned = BULLET_RE.sub('', stripped).strip()
            if cleaned:
                if student_ineligible_block:
                    student_ineligible_bullets.append(cleaned)
                    pending_blank = False
                    continue
                if has_reason_terms:
                    print(f"EXCLUDED BULLET: {cleaned}")
                    excluded_bullets.append(cleaned)
                else:
                    non_excluded_bullets.append(cleaned)
            pending_blank = False
    return excluded_bullets, non_excluded_bullets, student_ineligible_bullets


def is_value_line(text):
    return bool(re.search(r'[$%]', text)) or bool(re.search(r'\btuition fee\b', text, re.IGNORECASE))


def clean_value_line(text):
    cleaned = BULLET_RE.sub('', text.strip())
    return ' '.join(cleaned.split())


def collect_value_lines(text):
    value_lines = []
    for line in text.splitlines():
        cleaned = clean_value_line(line)
        if not cleaned:
            continue
        if is_value_line(cleaned):
            value_lines.append(cleaned)
    return value_lines


def is_list_item(line):
    return BULLET_RE.match(line) is not None


def clean_list_item(line):
    return BULLET_RE.sub('', line).strip()


def has_exclusion_trigger(lower_line):
    return any(trigger in lower_line for trigger in EXCLUSION_TRIGGERS)


def next_lines_contain_bullets(index, lines):
    line_count = len(lines)
    for offset in range(1, 4):
        look_index = index + offset
        if look_index >= line_count:
            break
        look_line = lines[look_index].strip()
        if not look_line:
            continue
        return is_list_item(look_line)
    return False


def insert_exclusion_sentence(stripped, lower_line, excluded_bullets):
    has_reason_terms = any(re.search(pattern, lower_line) for pattern in EXCLUSION_REASON_PATTERNS)
    if has_reason_terms:
        cleaned = BULLET_RE.sub('', stripped).strip()
        excluded_bullets.append(cleaned)


def classify_section(line, current_section, is_list):
    lower_line = line.lower()
    if not is_list and current_section == SECTION_EXCLUDED and is_heading_like(line):
        if not any(trigger in lower_line for trigger in EXCLUSION_TERMS):
            return SECTION_OTHER
    if current_section == SECTION_EXCLUDED and is_list:
        return current_section

    if any(trigger in lower_line for trigger in SECTION_TRIGGERS[SECTION_EXCLUDED]):
        return SECTION_EXCLUDED
    if any(trigger in lower_line for trigger in SECTION_TRIGGERS[SECTION_ELIGIBLE]):
        return SECTION_ELIGIBLE
    if any(trigger in lower_line for trigger in SECTION_TRIGGERS[SECTION_CONDITIONS]):
        return SECTION_CONDITIONS
    if any(trigger in lower_line for trigger in SECTION_TRIGGERS[SECTION_BENEFITS]):
        return SECTION_BENEFITS
    if '$' in line and current_section != SECTION_EXCLUDED:
        return SECTION_BENEFITS
    return current_section


def is_section_heading(line):
    normalized = line.strip().lower().rstrip(':').strip()
    for triggers in SECTION_TRIGGERS.values():
        if normalized in triggers:
            return True
    return False


def is_heading_like(line):
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) <= 60 and (stripped.endswith(':') or stripped.endswith('?')):
        return True
    return stripped.lower() in COMMON_HEADINGS


def extract_amounts(text):
    amounts = []
    for match in re.finditer(r'\$\s*([0-9][0-9,]*)', text):
        value = match.group(1).replace(',', '')
        if value.isdigit():
            amounts.append(int(value))
    return amounts


def normalize_advanced_standing_exclusion(text):
    lower_text = text.lower()
    level_prefix = 'GEN'
    if 'undergraduate' in lower_text or re.search(r'\bug\b', lower_text):
        level_prefix = 'UG'
    elif 'postgraduate' in lower_text or re.search(r'\bpg\b', lower_text):
        level_prefix = 'PG'

    number_match = re.search(r'(\d+)\s*(credit points?|cp)\b', lower_text)
    if not number_match:
        return f'{level_prefix}_ADVANCED_STANDING'

    number = number_match.group(1)
    comparator = 'CP'
    if re.search(r'\b(more than|greater than|over|exceed|above)\b', lower_text):
        comparator = f'GT_{number}CP'
    elif re.search(r'\b(at least|minimum|>=)\b', lower_text):
        comparator = f'GTE_{number}CP'
    else:
        comparator = f'{number}CP'
    return f'{level_prefix}_{comparator}'


def extract_eligibility_from_line(line, extracted):
    lower_line = line.lower()
    if 'international student' in lower_line:
        append_criteria(
            extracted,
            'demographic',
            'residency_status',
            'INTERNATIONAL',
            True,
            sentence=None,
            detect_exclusion=False
        )
    if re.search(r'\bundergraduate\b', lower_line):
        append_criteria(
            extracted,
            'academic_level',
            'level',
            'UNDERGRADUATE',
            True,
            sentence=None,
            detect_exclusion=False
        )
    if re.search(r'\bpostgraduate\b', lower_line):
        append_criteria(
            extracted,
            'academic_level',
            'level',
            'POSTGRADUATE',
            True,
            sentence=None,
            detect_exclusion=False
        )
    if re.search(r'\bnorth\s+asia\b', lower_line):
        append_criteria(
            extracted,
            'demographic',
            'origin_region',
            'NORTH_ASIA',
            True,
            sentence=None,
            detect_exclusion=False
        )
    if re.search(r'\bsouth[\s-]?east\s+asia\b', lower_line):
        append_criteria(
            extracted,
            'demographic',
            'origin_region',
            'SOUTHEAST_ASIA',
            True,
            sentence=None,
            detect_exclusion=False
        )
    if re.search(r'\b(completing|completed)?\s*australian year 12\b', lower_line):
        append_criteria(
            extracted,
            'academic_level',
            'prior_education',
            'AU_YEAR_12',
            True,
            sentence=None,
            detect_exclusion=False
        )
    if 'cricos' in lower_line or 'western sydney university' in lower_line:
        append_criteria(
            extracted,
            'location',
            'study_country',
            'AU',
            True,
            sentence=None,
            detect_exclusion=False
        )
    for state in STATE_CODES:
        if re.search(rf'\b{state}\b', line, re.IGNORECASE):
            if any(term in lower_line for term in ['study', 'campus', 'located', 'undertake', 'commence', 'attend']):
                append_criteria(
                    extracted,
                    'location',
                    'study_state',
                    state,
                    True,
                    sentence=None,
                    detect_exclusion=False
                )
            break

    # Gender
    if re.search(r'\b(women only|female students?|open to women|for women|women\'?s?)\b', lower_line):
        append_criteria(
            extracted, 'demographic', 'gender', 'Female', True,
            sentence=None, detect_exclusion=False
        )
    elif re.search(r'\b(men only|male only|male students? only)\b', lower_line):
        append_criteria(
            extracted, 'demographic', 'gender', 'Male', True,
            sentence=None, detect_exclusion=False
        )

    # Age — "mature age (25+)", "aged 25 or over", "25 years of age or older"
    age_match = re.search(
        r'\b(?:mature[\s-]?age|aged?\s+(\d{2})|(\d{2})\s*\+?\s*(?:years?\s*(?:of\s*age|or\s*(?:older|over))))\b',
        lower_line
    )
    if age_match:
        age_value = age_match.group(1) or age_match.group(2) or '25'
        append_criteria(
            extracted, 'demographic', 'age', age_value, True,
            sentence=None, detect_exclusion=False
        )

    # Institution — scholarship restricted to students of a specific university
    KNOWN_INSTITUTIONS = [
        'University of Sydney',
        'University of New South Wales',
        'UNSW Sydney',
        'UNSW',
        'University of Technology Sydney',
        'UTS',
        'Western Sydney University',
        'WSU',
        'University of Newcastle',
        'Macquarie University',
        'Australian National University',
        'ANU',
    ]
    institution_context = re.search(
        r'\b(students?\s+(?:of|at|enrolled\s+at|from)|enrolled\s+at|attending|undertaking\s+study\s+at)\b',
        lower_line
    )
    if institution_context:
        for institution in KNOWN_INSTITUTIONS:
            if institution.lower() in lower_line:
                append_criteria(
                    extracted, 'other', 'institution', institution, True,
                    sentence=None, detect_exclusion=False
                )
                break


def extract_exclusion_from_line(line, extracted):
    lower_line = line.lower()
    matched = False
    if 'australian citizen' in lower_line or 'citizen of australia' in lower_line:
        append_criteria(
            extracted,
            'demographic',
            'citizenship_excluded',
            'AU',
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True
    if 'new zealand citizen' in lower_line or 'citizen of new zealand' in lower_line:
        append_criteria(
            extracted,
            'demographic',
            'citizenship_excluded',
            'NZ',
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True
    if 'permanent resident' in lower_line and 'australia' in lower_line:
        append_criteria(
            extracted,
            'demographic',
            'residency_status_excluded',
            'PR_AU',
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True
    if 'higher degree research' in lower_line or re.search(r'\bhdr\b', lower_line):
        append_criteria(
            extracted,
            'academic_level',
            'level_excluded',
            'HDR',
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True
    if 'study abroad' in lower_line or 'exchange student' in lower_line or 'exchange' in lower_line:
        append_criteria(
            extracted,
            'other',
            'exchange_excluded',
            'TRUE',
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True
    if 'sydney city campus' in lower_line:
        append_criteria(
            extracted,
            'location',
            'campus_excluded',
            'SYDNEY_CITY',
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True
    if 'advanced standing' in lower_line or 'credit points' in lower_line or re.search(r'\bcp\b', lower_line):
        append_criteria(
            extracted,
            'other',
            'advanced_standing_excluded',
            normalize_advanced_standing_exclusion(line),
            True,
            sentence=line,
            force_excluded=True
        )
        matched = True

    if not matched:
        fallback_value = line[:255].strip()
        if fallback_value and not _is_junk_exclusion(fallback_value):
            append_criteria(
                extracted,
                'other',
                'ineligible_condition_excluded',
                fallback_value,
                True,
                sentence=line,
                force_excluded=True
            )


def extract_sectioned_rules(text):
    extracted = []
    benefit_lines = []
    condition_lines = []
    amount_values = []
    manual_notes = []
    if not text:
        return extracted, benefit_lines, condition_lines, amount_values, manual_notes

    current_section = SECTION_OTHER
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_list = is_list_item(stripped)
        lower_line = stripped.lower()
        if any(term in lower_line for term in EXCLUSION_TERMS):
            current_section = SECTION_EXCLUDED
        elif any(term in lower_line for term in INCLUSION_TERMS):
            current_section = SECTION_ELIGIBLE
        else:
            current_section = classify_section(stripped, current_section, is_list)
        content = clean_list_item(stripped) if is_list else stripped
        if not content:
            continue
        if not is_list and is_section_heading(content):
            continue
        if not is_list and len(content) > 220:
            continue
        if any(term in lower_line for term in OVERRIDE_TERMS):
            manual_notes.append(content)
        if current_section == SECTION_ELIGIBLE:
            extract_eligibility_from_line(content, extracted)
        elif current_section == SECTION_EXCLUDED:
            extract_exclusion_from_line(content, extracted)
        elif current_section == SECTION_BENEFITS:
            benefit_lines.append(content)
            amount_values.extend(extract_amounts(content))
        elif current_section == SECTION_CONDITIONS:
            condition_lines.append(content)

    return extracted, benefit_lines, condition_lines, amount_values, manual_notes


def extract_rules_from_text(text):
    extracted = []
    benefit_lines = []
    condition_lines = []
    if not text:
        return extracted, benefit_lines

    text_lower = text.lower()
    hdr_match = re.search(r'\bhdr\b', text_lower)
    if hdr_match:
        sentence = find_sentence(text, hdr_match.start(), hdr_match.end())
        append_criteria(
            extracted,
            'academic_level',
            'level_excluded',
            'HDR',
            True,
            sentence=sentence,
            force_excluded=True
        )

    excluded_bullets, non_excluded_bullets, student_ineligible_bullets = parse_exclusion_bullets(text)
    if student_ineligible_bullets:
        for bullet in student_ineligible_bullets:
            bullet_lower = bullet.lower()
            sentence = bullet
            if re.search(r'\b(hdr|ph\.?d|higher degree by research|doctor of philosophy)\b', bullet_lower):
                append_criteria(
                    extracted,
                    'academic_level',
                    'level_excluded',
                    'HDR',
                    True,
                    sentence=sentence,
                    force_excluded=True
                )
            if re.search(r'\b(australia|australian)\b', bullet_lower) and 'citizen' in bullet_lower:
                append_criteria(
                    extracted,
                    'demographic',
                    'citizenship_excluded',
                    'AU',
                    True,
                    sentence=sentence,
                    force_excluded=True
                )
            if re.search(r'\b(new zealand|nz)\b', bullet_lower) and 'citizen' in bullet_lower:
                append_criteria(
                    extracted,
                    'demographic',
                    'citizenship_excluded',
                    'NZ',
                    True,
                    sentence=sentence,
                    force_excluded=True
                )
            if 'permanent resident' in bullet_lower and re.search(r'\b(australia|australian)\b', bullet_lower):
                append_criteria(
                    extracted,
                    'demographic',
                    'residency_status_excluded',
                    'PR_AU',
                    True,
                    sentence=sentence,
                    force_excluded=True
                )

        exclusion_set = {bullet.strip() for bullet in student_ineligible_bullets}
        if exclusion_set:
            filtered_lines = []
            for line in text.splitlines():
                cleaned_line = BULLET_RE.sub('', line.strip()).strip()
                if cleaned_line in exclusion_set:
                    continue
                filtered_lines.append(line)
            text = '\n'.join(filtered_lines)

    text_lower = text.lower()
    upper_text = text.upper()
    hdr_exclusion_lines = []
    for bullet in excluded_bullets:
        bullet_lower = bullet.lower()
        inserted_any = False
        if re.search(r'\b(hdr|ph\.?d|higher degree by research|doctor of philosophy)\b', bullet_lower):
            append_criteria(
                extracted,
                'academic_level',
                'level_excluded',
                'HDR',
                True,
                sentence=bullet,
                force_excluded=True
            )
            hdr_exclusion_lines.append(bullet)
            inserted_any = True
        if re.search(r'\b(australian citizen|australian citizens)\b', bullet_lower):
            append_criteria(
                extracted,
                'demographic',
                'citizenship_excluded',
                'AU',
                True,
                sentence=bullet,
                force_excluded=True
            )
            inserted_any = True
        if re.search(r'\bpermanent resident(s)?\b', bullet_lower):
            append_criteria(
                extracted,
                'demographic',
                'residency_status_excluded',
                'PR',
                True,
                sentence=bullet,
                force_excluded=True
            )
            inserted_any = True
        if re.search(r'\b(new zealand|nz)\b', bullet_lower):
            append_criteria(
                extracted,
                'demographic',
                'citizenship_excluded',
                'NZ',
                True,
                sentence=bullet,
                force_excluded=True
            )
            inserted_any = True
        if re.search(r'\bexchange\b', bullet_lower):
            append_criteria(
                extracted,
                'other',
                'enrolment_type',
                'EXCHANGE',
                True,
                sentence=bullet,
                force_excluded=True
            )
            inserted_any = True
        campus_match = re.search(r'\b([A-Za-z][A-Za-z ]{2,})\s+campus\b', bullet)
        if campus_match:
            append_criteria(
                extracted,
                'other',
                'study_location',
                campus_match.group(1).strip() + ' campus',
                True,
                sentence=bullet,
                force_excluded=True
            )
            inserted_any = True
        elif 'campus' in bullet_lower:
            append_criteria(
                extracted,
                'other',
                'study_location',
                bullet,
                True,
                sentence=bullet,
                force_excluded=True
            )
            inserted_any = True
        if not inserted_any:
            fallback_value = bullet[:255].strip()
            if fallback_value and not _is_junk_exclusion(fallback_value):
                append_criteria(
                    extracted,
                    'other',
                    'ineligible_condition_excluded',
                    fallback_value,
                    True,
                    sentence=bullet,
                    force_excluded=True
                )
    for bullet in non_excluded_bullets:
        fallback_value = bullet[:255].strip()
        if is_value_line(bullet):
            benefit_lines.append(fallback_value)
            continue
        condition_lines.append(fallback_value)

    if hdr_exclusion_lines:
        exclusion_set = {line.strip() for line in hdr_exclusion_lines}
        filtered_lines = []
        for line in text.splitlines():
            cleaned_line = BULLET_RE.sub('', line.strip()).strip()
            if cleaned_line in exclusion_set:
                continue
            filtered_lines.append(line)
        text = '\n'.join(filtered_lines)
        text_lower = text.lower()
        upper_text = text.upper()

    for state in ['NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT']:
        for match in re.finditer(rf'\b{state}\b', upper_text):
            sentence = find_sentence(text, match.start(), match.end())
            append_criteria(
                extracted,
                'location',
                'study_state',
                state,
                infer_is_required(sentence),
                sentence=sentence
            )
            break

    study_country_patterns = [
        r'\bstudy in australia\b',
        r'\bstudying in australia\b',
        r'\benrolled in australia\b',
        r'\bat an australian university\b',
        r'\baustralian year 12\b'
    ]
    for pattern in study_country_patterns:
        match = re.search(pattern, text_lower)
        if match:
            sentence = find_sentence(text, match.start(), match.end())
            append_criteria(
                extracted,
                'location',
                'study_country',
                'AU',
                infer_is_required(sentence),
                sentence=sentence
            )
            break

    not_citizen = re.search(r'\bnot (an )?australian citizen\b', text_lower)
    not_pr = re.search(r'\bnot (a )?permanent resident\b', text_lower)
    if not_citizen or not_pr:
        sentence = find_sentence(
            text,
            (not_citizen or not_pr).start(),
            (not_citizen or not_pr).end()
        )
        append_criteria(
            extracted,
            'demographic',
            'residency_status',
            'INTERNATIONAL',
            infer_is_required(sentence),
            sentence=sentence
        )

    if 'international student' in text_lower:
        index = text_lower.find('international student')
        sentence = find_sentence(text, index, index + len('international student'))
        append_criteria(
            extracted,
            'demographic',
            'residency_status',
            'INTERNATIONAL',
            infer_is_required(sentence),
            sentence=sentence
        )
    if 'australian citizen' in text_lower and not not_citizen:
        index = text_lower.find('australian citizen')
        sentence = find_sentence(text, index, index + len('australian citizen'))
        append_criteria(
            extracted,
            'demographic',
            'residency_status',
            'CITIZEN',
            infer_is_required(sentence),
            sentence=sentence
        )
    if 'permanent resident' in text_lower and not not_pr:
        index = text_lower.find('permanent resident')
        sentence = find_sentence(text, index, index + len('permanent resident'))
        append_criteria(
            extracted,
            'demographic',
            'residency_status',
            'PR',
            infer_is_required(sentence),
            sentence=sentence
        )
    if 'domestic student' in text_lower:
        index = text_lower.find('domestic student')
        sentence = find_sentence(text, index, index + len('domestic student'))
        append_criteria(
            extracted,
            'demographic',
            'residency_status',
            'CITIZEN_OR_PR',
            infer_is_required(sentence),
            sentence=sentence
        )

    origin_region_patterns = [
        (r'\bnorth\s+asia\b', 'NORTH_ASIA'),
        (r'\bsouth[\s-]?east\s+asia\b', 'SOUTHEAST_ASIA')
    ]
    for pattern, region_value in origin_region_patterns:
        match = re.search(pattern, text_lower)
        if match:
            sentence = find_sentence(text, match.start(), match.end())
            append_criteria(
                extracted,
                'demographic',
                'origin_region',
                region_value,
                True,
                sentence=sentence
            )

    if re.search(r'\bfull[-\s]?time\b', text_lower):
        match = re.search(r'\bfull[-\s]?time\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_load',
            'FULL_TIME',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\b75\s*%|three[-\s]quarter[-\s]time\b', text_lower):
        match = re.search(r'\b75\s*%|three[-\s]quarter[-\s]time\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_load',
            'PART_TIME_75',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\b50\s*%|half[-\s]time\b', text_lower):
        match = re.search(r'\b50\s*%|half[-\s]time\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_load',
            'PART_TIME_50',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\b25\s*%|quarter[-\s]time\b', text_lower):
        match = re.search(r'\b25\s*%|quarter[-\s]time\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_load',
            'PART_TIME_25',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\bpart[-\s]?time\b', text_lower):
        match = re.search(r'\bpart[-\s]?time\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_load',
            'PART_TIME',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\bon[-\s]campus\b|\binternal(?:ly)?\b', text_lower):
        match = re.search(r'\bon[-\s]campus\b|\binternal(?:ly)?\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_mode',
            'ON_CAMPUS',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\bonline\b|\bdistance\b|\bexternal(?:ly)?\b', text_lower):
        match = re.search(r'\bonline\b|\bdistance\b|\bexternal(?:ly)?\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_mode',
            'ONLINE',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\bhybrid\b|\bblended\b', text_lower):
        match = re.search(r'\bhybrid\b|\bblended\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'study_mode',
            'HYBRID',
            infer_is_required(sentence),
            sentence=sentence
        )

    if re.search(r'\b(undergraduate|bachelor|ug)\b', text_lower):
        match = re.search(r'\b(undergraduate|bachelor|ug)\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'level',
            'UNDERGRADUATE',
            infer_is_required(sentence),
            sentence=sentence
        )
    if re.search(r'\b(postgraduate|master|pg)\b', text_lower):
        match = re.search(r'\b(postgraduate|master|pg)\b', text_lower)
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'academic_level',
            'level',
            'POSTGRADUATE',
            infer_is_required(sentence),
            sentence=sentence
        )
    hdr_match = re.search(r'\b(ph\.?d|doctor of philosophy|higher degree by research|higher degree research)\b', text_lower)
    if hdr_match:
        sentence = find_sentence(text, hdr_match.start(), hdr_match.end())
        append_criteria(
            extracted,
            'academic_level',
            'level_excluded',
            'HDR',
            True,
            sentence=sentence,
            force_excluded=True
        )

    if 'full-fee paying' in text_lower:
        index = text_lower.find('full-fee paying')
        sentence = find_sentence(text, index, index + len('full-fee paying'))
        append_criteria(
            extracted,
            'other',
            'fee_status',
            'FULL_FEE',
            infer_is_required(sentence),
            sentence=sentence
        )

    for pattern in COUNTRY_CONTEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            country = match.group(1)
            clause = find_sentence(text, match.start(), match.end())
            clause_lower = clause.lower()
            if any(term in clause_lower for term in ['not', 'excluding', 'ineligible', 'must not be']):
                country_value = country
                if country.lower() == 'australia':
                    country_value = 'AU'
                elif country.lower() == 'new zealand':
                    country_value = 'NZ'
                append_criteria(
                    extracted,
                    'demographic',
                    'citizenship_excluded',
                    country_value,
                    True,
                    sentence=clause,
                    force_excluded=True
                )
                break
            if re.search(rf'\b{re.escape(country)}\s+citizens?\b', match.group(0), re.IGNORECASE):
                if 'not' in clause_lower:
                    country_value = country
                    if country.lower() == 'australia':
                        country_value = 'AU'
                    elif country.lower() == 'new zealand':
                        country_value = 'NZ'
                    append_criteria(
                        extracted,
                        'demographic',
                        'citizenship_excluded',
                        country_value,
                        True,
                        sentence=clause,
                        force_excluded=True
                    )
                    break
            if country.lower() != 'australia':
                append_criteria(
                    extracted,
                    'demographic',
                    'nationality',
                    country,
                    infer_is_required(clause),
                    sentence=clause
                )
            break
    else:
        demonym_match = DEMONYM_CONTEXT_PATTERN.search(text)
        if demonym_match:
            demonym = demonym_match.group(1).lower()
            country = DEMONYMS.get(demonym)
            if country and country.lower() != 'australia':
                clause = find_sentence(text, demonym_match.start(), demonym_match.end())
                clause_lower = clause.lower()
                if any(term in clause_lower for term in ['not', 'excluding', 'ineligible', 'must not be']):
                    country_value = country
                    if country.lower() == 'new zealand':
                        country_value = 'NZ'
                    append_criteria(
                        extracted,
                        'demographic',
                        'citizenship_excluded',
                        country_value,
                        True,
                        sentence=clause,
                        force_excluded=True
                    )
                else:
                    append_criteria(
                        extracted,
                        'demographic',
                        'nationality',
                        country,
                        infer_is_required(clause),
                        sentence=clause
                    )

    return extracted, benefit_lines, condition_lines


def extract_page_exclusions(text):
    extracted = []
    if not text:
        return extracted
    text_lower = text.lower()
    exclusions = [
        ('Medicine/MD', [r'\bmedicine\b', r'\bmd\b', r'\bdoctor of medicine\b']),
        ('Nursing', [r'\bnursing\b']),
        ('Master of Nursing Practice', [r'\bmaster of nursing practice\b']),
        ('Master of Research', [r'\bmaster of research\b']),
        ('HDR', [r'\bph\.?d\b', r'\bdoctor of philosophy\b', r'\bhigher degree by research\b']),
        ('WSUSCC campus/offshore', [r'\bwsuscc\b', r'\boffshore\b'])
    ]
    for label, patterns in exclusions:
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                sentence = find_sentence(text, match.start(), match.end())
                criteria_key = 'ineligible_program'
                if label == 'Master of Research':
                    criteria_key = 'program_excluded'
                append_criteria(
                    extracted,
                    'other',
                    criteria_key,
                    label,
                    True,
                    sentence=sentence,
                    force_excluded=True
                )
                break

    match = re.search(r'\bsydney city campus\b', text_lower)
    if match:
        sentence = find_sentence(text, match.start(), match.end())
        append_criteria(
            extracted,
            'other',
            'study_location_exclusion',
            'Sydney City campus',
            True,
            sentence=sentence,
            force_excluded=True
        )

    return extracted


def normalize_criteria_rows(rows):
    normalized = []
    seen = set()
    for criteria in rows:
        criteria_type = normalize_criteria_type(criteria['criteria_type'])
        criteria_key = normalize_criteria_key(criteria['criteria_key'])
        if not criteria_key and criteria_type in {'location', 'demographic'}:
            continue
        if not criteria_key:
            criteria_key = normalize_criteria_key(criteria_type)
        if not validate_criteria_key(criteria_type, criteria_key):
            continue
        required_value = str(criteria['required_value']).strip()
        if not required_value:
            continue
        dedupe_key = (criteria_type, criteria_key, required_value.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append({
            'criteria_type': criteria_type,
            'criteria_key': criteria_key,
            'required_value': required_value,
            'is_required': bool(criteria.get('is_required', True))
        })
    excluded_concepts = set()
    for item in normalized:
        criteria_key = item['criteria_key']
        if criteria_key in {'level_excluded', 'level_exclusion'}:
            base_key = 'level'
        elif criteria_key.endswith('_excluded'):
            base_key = criteria_key[:-9]
        elif criteria_key.endswith('_exclusion'):
            base_key = criteria_key[:-10]
        else:
            continue
        excluded_concepts.add((item['criteria_type'], base_key, item['required_value'].lower()))
    if excluded_concepts:
        normalized = [
            item for item in normalized
            if (item['criteria_type'], item['criteria_key'], item['required_value'].lower()) not in excluded_concepts
        ]
    normalized = [
        item for item in normalized
        if not (
            item['criteria_type'] == 'academic_level'
            and item['criteria_key'] == 'level'
            and item['required_value'].strip().upper() == 'HDR'
        )
    ]
    has_hdr_excluded = any(
        item['criteria_type'] == 'academic_level'
        and item['required_value'].strip().upper() == 'HDR'
        and (
            item['criteria_key'] in {'level_excluded', 'level__excluded', 'level_exclusion'}
            or item['criteria_key'].endswith('_excluded')
        )
        for item in normalized
    )
    has_au_citizenship_excluded = any(
        item['criteria_type'] == 'demographic'
        and item['criteria_key'] == 'citizenship_excluded'
        and item['required_value'].strip().upper() in {'AU', 'AUSTRALIA', 'AUSTRALIAN'}
        for item in normalized
    )
    has_pr_au_excluded = any(
        item['criteria_type'] == 'demographic'
        and item['criteria_key'] == 'residency_status_excluded'
        and item['required_value'].strip().upper() == 'PR_AU'
        for item in normalized
    )
    if has_hdr_excluded or has_au_citizenship_excluded or has_pr_au_excluded:
        filtered = []
        for item in normalized:
            if has_hdr_excluded:
                if (
                    item['criteria_type'] == 'academic_level'
                    and item['criteria_key'] == 'level'
                    and item['required_value'].strip().upper() == 'HDR'
                ):
                    continue
            if has_au_citizenship_excluded:
                if (
                    item['criteria_type'] == 'demographic'
                    and item['criteria_key'] == 'nationality'
                    and item['required_value'].strip().upper() in {'AU', 'AUSTRALIA', 'AUSTRALIAN'}
                ):
                    continue
            if has_pr_au_excluded:
                if (
                    item['criteria_type'] == 'demographic'
                    and item['criteria_key'] == 'residency_status'
                    and item['required_value'].strip().upper() in {'PR', 'CITIZEN', 'CITIZEN_OR_PR'}
                ):
                    continue
            filtered.append(item)
        normalized = filtered
    study_load_values = {
        item['required_value'].upper()
        for item in normalized
        if item['criteria_type'] == 'other' and item['criteria_key'] == 'study_load'
    }
    if {'FULL_TIME', 'PART_TIME'}.issubset(study_load_values):
        for item in normalized:
            if item['criteria_type'] == 'other' and item['criteria_key'] == 'study_load':
                item['is_required'] = True
    return normalized


def main():
    parser = argparse.ArgumentParser(description='Normalize eligibility from sources.')
    parser.add_argument('--ids', help='Comma-separated scholarship IDs to process.')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()

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
            scholarships = conn.execute(
                stmt,
                {'ids': [int(item) for item in ids]}
            ).fetchall()
        else:
            scholarships = conn.execute(text('''
                SELECT id, application_url
                FROM scholarships
                WHERE application_url IS NOT NULL
                AND application_url != ''
            ''')).fetchall()

        for scholarship in scholarships:
            global CURRENT_SCHOLARSHIP_ID
            CURRENT_SCHOLARSHIP_ID = scholarship.id
            sources = conn.execute(text('''
                SELECT url, content_type, raw_text
                FROM scholarship_sources
                WHERE scholarship_id = :scholarship_id
                ORDER BY fetched_at DESC
            '''), {'scholarship_id': scholarship.id}).fetchall()

            if not sources:
                continue

            main_text = ''
            related_texts = []
            for source in sources:
                if source.url == scholarship.application_url and source.content_type == 'html':
                    main_text = source.raw_text or ''
                elif source.raw_text:
                    related_texts.append(source.raw_text)

            if not main_text and sources:
                main_text = sources[0].raw_text or ''

            source_text = '\n'.join([main_text] + related_texts).strip()
            source_text = clean_source_text(source_text)
            conn.execute(text('''
                UPDATE scholarships
                SET eligibility_raw_text = :eligibility_raw_text
                WHERE id = :scholarship_id
            '''), {
                'eligibility_raw_text': source_text,
                'scholarship_id': scholarship.id
            })

            criteria_rows = []
            extracted_rows, benefit_lines, condition_lines, amount_values, manual_notes = extract_sectioned_rules(source_text)
            criteria_rows.extend(extracted_rows)
            for note in manual_notes:
                trimmed = note[:255].strip()
                if trimmed:
                    append_criteria(
                        criteria_rows,
                        'other',
                        'manual_review_note',
                        trimmed,
                        True,
                        sentence=note,
                        detect_exclusion=False
                    )
            criteria_rows.extend(extract_page_exclusions(main_text))

            if benefit_lines or condition_lines or amount_values:
                seen_values = set()
                deduped_values = []
                for line in benefit_lines:
                    key = line.lower()
                    if key in seen_values:
                        continue
                    seen_values.add(key)
                    deduped_values.append(line)

                amount_row = conn.execute(text('''
                    SELECT amount, benefits_text, conditions_text
                    FROM scholarships
                    WHERE id = :scholarship_id
                '''), {'scholarship_id': scholarship.id}).fetchone()
                current_amount = amount_row.amount if amount_row else None
                current_benefits = amount_row.benefits_text if amount_row else None
                current_conditions = amount_row.conditions_text if amount_row else None
                updates = {}
                if not current_amount and amount_values:
                    updates['amount'] = max(amount_values)
                if deduped_values:
                    new_text = '\n'.join(deduped_values)
                    if current_benefits:
                        if args.replace:
                            updates['benefits_text'] = new_text
                        else:
                            existing_lower = current_benefits.lower()
                            to_add = [
                                line for line in deduped_values
                                if line.lower() not in existing_lower
                            ]
                            if to_add:
                                updates['benefits_text'] = current_benefits.rstrip() + '\n' + '\n'.join(to_add)
                    else:
                        updates['benefits_text'] = new_text
                if condition_lines:
                    deduped_conditions = []
                    seen_conditions = set()
                    for line in condition_lines:
                        key = line.lower()
                        if key in seen_conditions:
                            continue
                        seen_conditions.add(key)
                        deduped_conditions.append(line)
                    new_conditions_text = '\n'.join(deduped_conditions)
                    if current_conditions:
                        if args.replace:
                            updates['conditions_text'] = new_conditions_text
                        else:
                            existing_lower = current_conditions.lower()
                            to_add = [
                                line for line in deduped_conditions
                                if line.lower() not in existing_lower
                            ]
                            if to_add:
                                updates['conditions_text'] = current_conditions.rstrip() + '\n' + '\n'.join(to_add)
                    else:
                        updates['conditions_text'] = new_conditions_text
                if updates:
                    updates['scholarship_id'] = scholarship.id
                    updates.setdefault('amount', None)
                    updates.setdefault('benefits_text', None)
                    updates.setdefault('conditions_text', None)
                    conn.execute(text('''
                        UPDATE scholarships
                        SET amount = COALESCE(:amount, amount),
                            benefits_text = COALESCE(:benefits_text, benefits_text),
                            conditions_text = COALESCE(:conditions_text, conditions_text)
                        WHERE id = :scholarship_id
                    '''), updates)

            normalized = normalize_criteria_rows(criteria_rows)

            if not normalized:
                snippet = (source_text or '').strip()[:255]
                if snippet:
                    normalized = [{
                        'criteria_type': 'other',
                        'criteria_key': 'raw_text',
                        'required_value': snippet,
                        'is_required': False
                    }]

            if args.replace:
                conn.execute(
                    text('''
                        DELETE FROM eligibility_criteria
                        WHERE scholarship_id = :sid
                        AND criteria_type = 'academic_level'
                        AND criteria_key = 'level'
                        AND required_value = 'HDR'
                    '''),
                    {'sid': scholarship.id}
                )
                conn.execute(
                    text('DELETE FROM eligibility_criteria WHERE scholarship_id = :sid'),
                    {'sid': scholarship.id}
                )

            for criteria in normalized:
                conn.execute(text('''
                    INSERT IGNORE INTO eligibility_criteria
                    (scholarship_id, criteria_type, criteria_key, required_value, is_required)
                    VALUES
                    (:scholarship_id, :criteria_type, :criteria_key, :required_value, :is_required)
                '''), {
                    'scholarship_id': scholarship.id,
                    'criteria_type': criteria['criteria_type'],
                    'criteria_key': criteria['criteria_key'],
                    'required_value': criteria['required_value'],
                    'is_required': int(criteria['is_required'])
                })


if __name__ == '__main__':
    main()
