import json
import re

ALLOWED_CRITERIA_TYPES = {
    'academic_level',
    'gpa',
    'field_of_study',
    'demographic',
    'location',
    'financial_need',
    'extracurricular',
    'other'
}

# Keys allowed under every criteria type (catch-all / fallback keys).
_UNIVERSAL_KEYS = {'raw_text', 'manual_review_note'}

ALLOWED_KEYS: dict = {
    'academic_level':  {'degree_level', 'year_of_study', 'study_load', 'enrollment_status',
                        'prior_education', 'level', 'study_mode'},
    'gpa':             {'minimum_gpa', 'academic_standing'},
    'field_of_study':  {'discipline', 'major'},
    'demographic':     {'citizenship', 'residency_status', 'nationality', 'origin_region',
                        'gender', 'age', 'background', 'indigenous_status',
                        # Cross-type keys Claude sometimes sends under demographic:
                        'employment_status', 'home_state', 'study_country'},
    'location':        {'study_state', 'study_country', 'home_state', 'citizenship', 'residency_status'},
    'financial_need':  {'income_threshold', 'means_tested'},
    'extracurricular': {'community_involvement', 'leadership', 'sport'},
    'other':           {'visa_status', 'disability', 'employment_status', 'institution',
                        'study_load', 'fee_status', 'enrollment_status',
                        'ineligible_condition_excluded', 'ineligible_program_excluded',
                        'prior_education', 'gaokao_completion_timeframe'},
}

YEAR_OF_STUDY_VALUE_MAP: dict = {
    'commencing':  'YEAR_1',
    'first year':  'YEAR_1', '1st year': 'YEAR_1', 'year 1': 'YEAR_1', 'year one': 'YEAR_1',
    'second year': 'YEAR_2', '2nd year': 'YEAR_2', 'year 2': 'YEAR_2', 'year two': 'YEAR_2',
    'third year':  'YEAR_3', '3rd year': 'YEAR_3', 'year 3': 'YEAR_3', 'year three': 'YEAR_3',
    'fourth year': 'YEAR_4', '4th year': 'YEAR_4', 'year 4': 'YEAR_4', 'year four': 'YEAR_4',
    'final year':  'FINAL_YEAR', 'last year': 'FINAL_YEAR',
}

KEY_ALIASES: dict = {
    # Academic level
    'study_level':           'degree_level',
    'academic_year':         'year_of_study',
    'year':                  'year_of_study',
    'enrollment':            'enrollment_status',
    'enrolment_status':      'enrollment_status',
    'career_stage':          'enrollment_status',    # e.g. "First three years of teaching"
    'new_student_status':    'enrollment_status',    # e.g. "New commencing student"
    'current_student_status':'enrollment_status',    # e.g. "Not a current student"
    # GPA
    'gpa_minimum':           'minimum_gpa',
    'minimum_grade':         'minimum_gpa',
    # Field of study
    'field':                 'discipline',
    'course':                'discipline',
    'area_of_study':         'discipline',
    # Demographic
    'residency':             'residency_status',
    'citizen':               'citizenship',
    'region':                'origin_region',
    'home_country':          'nationality',
    'eligible_country':      'study_country',        # → location key allowed in demographic
    'employment':            'employment_status',     # e.g. "Public school teacher"
    'professional_membership': 'manual_review_note', # e.g. "NSWNMA member required"
    'membership_requirement':  'manual_review_note', # e.g. "Federation Student Member"
    # Location
    'state':                 'study_state',
    'country':               'study_country',
    'regional_rural_remote': 'home_state',           # e.g. "Must live in regional area"
    # Financial
    'income':                'income_threshold',
    'financial_status':      'means_tested',
    'financial_need':        'means_tested',         # key used under financial_need type
    # Extracurricular
    'community':             'community_involvement',
    # Other
    'visa':                  'visa_status',
    'indigenous':            'indigenous_status',
}

CRITERIA_TYPE_ALIASES = {
    'academic level':   'academic_level',
    'academic_level':   'academic_level',
    'academiclevel':    'academic_level',
    'demographics':     'demographic',
    'demographic':      'demographic',
    'field of study':   'field_of_study',
    'field_of_study':   'field_of_study',
    'industry':         'field_of_study',
    'location':         'location',
    'gpa':              'gpa',
    'financial':        'financial_need',
    'financial need':   'financial_need',
    'financial_need':   'financial_need',
    'extracurricular':  'extracurricular',
    'other':            'other',
}


def log_normalized_criteria(scholarship_id, source_url, original_value, criteria):
    log_entry = {
        'scholarship_id': scholarship_id,
        'source_url': source_url,
        'original_criteria_type': original_value,
        'criteria': criteria
    }
    with open('normalized_criteria_log.jsonl', 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(log_entry) + '\n')


def normalize_criteria_type(value, scholarship_id=None, source_url=None, criteria=None):
    if not value:
        return 'other'
    normalized = re.sub(r'\s+', ' ', str(value).strip().lower())
    normalized = CRITERIA_TYPE_ALIASES.get(normalized, normalized.replace(' ', '_'))
    if normalized not in ALLOWED_CRITERIA_TYPES:
        log_normalized_criteria(scholarship_id, source_url, value, criteria)
        return 'other'
    return normalized


def normalize_criteria_key(value):
    if not value:
        return None
    normalized = re.sub(r'\s+', '_', str(value).strip().lower())
    return KEY_ALIASES.get(normalized, normalized) or None


def normalize_criteria_value(criteria_type, criteria_key, value):
    if not value:
        return value
    if criteria_type == 'academic_level' and criteria_key == 'year_of_study':
        return YEAR_OF_STUDY_VALUE_MAP.get(value.strip().lower(), value)
    if criteria_type == 'academic_level' and criteria_key == 'study_load':
        v = value.strip().lower()
        if 'full' in v:
            return 'FULL_TIME'
        if '75' in v or 'three-quarter' in v or 'three quarter' in v:
            return 'PART_TIME_75'
        if '50' in v or 'half' in v:
            return 'PART_TIME_50'
        if '25' in v or 'quarter' in v:
            return 'PART_TIME_25'
        if 'part' in v:
            return 'PART_TIME'
    if criteria_type == 'academic_level' and criteria_key == 'study_mode':
        v = value.strip().lower()
        if 'campus' in v or 'internal' in v:
            return 'ON_CAMPUS'
        if 'online' in v or 'distance' in v or 'external' in v:
            return 'ONLINE'
        if 'hybrid' in v or 'blend' in v or 'mixed' in v:
            return 'HYBRID'
    return value


def validate_criteria_key(criteria_type, criteria_key):
    if not isinstance(criteria_key, str):
        return False
    # Universal keys are valid under any criteria type.
    if criteria_key in _UNIVERSAL_KEYS:
        return True
    allowed = ALLOWED_KEYS.get(criteria_type)
    if allowed is None:
        return False
    # Direct match — catches keys like 'ineligible_condition_excluded' that are
    # stored with the suffix already in the allowlist.
    if criteria_key in allowed:
        return True
    # Dynamic exclusion suffix — e.g. 'study_mode_excluded' → check 'study_mode'
    if criteria_key.endswith('_excluded') or criteria_key.endswith('_exclusion'):
        base = re.sub(r'_(excluded|exclusion)$', '', criteria_key)
        return base in allowed
    return False
