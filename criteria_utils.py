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

ALLOWED_LOCATION_KEYS = {
    'study_state',
    'study_country'
}

ALLOWED_DEMOGRAPHIC_KEYS = {
    'citizenship',
    'residency_status',
    'nationality',
    'origin_region'
}

CRITERIA_TYPE_ALIASES = {
    'academic level': 'academic_level',
    'academic_level': 'academic_level',
    'academiclevel': 'academic_level',
    'demographics': 'demographic',
    'demographic': 'demographic',
    'field of study': 'field_of_study',
    'field_of_study': 'field_of_study',
    'industry': 'field_of_study'
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
    return normalized or None


def validate_criteria_key(criteria_type, criteria_key):
    if isinstance(criteria_key, str) and (
        criteria_key.endswith('_excluded') or criteria_key.endswith('_exclusion')
    ):
        return True
    if criteria_type == 'academic_level' and criteria_key in {'prior_education', 'level'}:
        return True
    if criteria_type == 'location':
        if criteria_key in ALLOWED_LOCATION_KEYS:
            return True
        if criteria_key.endswith('_excluded'):
            return criteria_key[:-9] in ALLOWED_LOCATION_KEYS
        if criteria_key.endswith('_exclusion'):
            return criteria_key[:-10] in ALLOWED_LOCATION_KEYS
        return False
    if criteria_type == 'demographic':
        if criteria_key in ALLOWED_DEMOGRAPHIC_KEYS:
            return True
        if criteria_key.endswith('_excluded'):
            return criteria_key[:-9] in ALLOWED_DEMOGRAPHIC_KEYS
        if criteria_key.endswith('_exclusion'):
            return criteria_key[:-10] in ALLOWED_DEMOGRAPHIC_KEYS
        return False
    return True
