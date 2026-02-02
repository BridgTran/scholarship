from datetime import datetime
import json
import logging
import re

from flask import Blueprint, request, jsonify
from sqlalchemy import text

from db import engine
from criteria_utils import normalize_criteria_type, normalize_criteria_key, validate_criteria_key

bp_detail = Blueprint('scholarship_detail', __name__)


@bp_detail.route('/api/scholarships/<int:scholarship_id>', methods=['GET'])
def get_scholarship_detail(scholarship_id):
    '''Retrieves complete information for a specific scholarship including eligibility criteria'''
    try:
        # Input validation
        if scholarship_id <= 0:
            return jsonify({'error': 'Invalid scholarship ID'}), 400

        with engine.connect() as conn:
            # Get main scholarship information with organization details
            scholarship_query = text('''
                SELECT 
                    s.id,
                    s.title,
                    s.description,
                    s.amount,
                    s.benefits_text,
                    s.deadline,
                    s.application_url,
                    s.industry,
                    s.status,
                    s.created_at,
                    o.id as organization_id,
                    o.name as organization_name,
                    o.type as organization_type,
                    o.website as organization_website,
                    o.jurisdiction_state,
                    o.jurisdiction_country
                FROM scholarships s
                JOIN organizations o ON s.organization_id = o.id
                WHERE s.id = :scholarship_id
            ''')

            scholarship_result = conn.execute(scholarship_query, {'scholarship_id': scholarship_id})
            scholarship_row = scholarship_result.first()

            if not scholarship_row:
                return jsonify({'error': 'Scholarship not found'}), 404

            # Get eligibility criteria
            criteria_query = text('''
                SELECT 
                    id,
                    criteria_type,
                    criteria_key,
                    required_value,
                    is_required,
                    inclusion_keywords,
                    exclusion_keywords
                FROM eligibility_criteria
                WHERE scholarship_id = :scholarship_id
                ORDER BY is_required DESC, criteria_type, id
            ''')

            criteria_result = conn.execute(criteria_query, {'scholarship_id': scholarship_id})
            eligibility_criteria = []

            for criteria_row in criteria_result:
                eligibility_criteria.append({
                    'id': criteria_row.id,
                    'type': criteria_row.criteria_type,
                    'criteria_key': criteria_row.criteria_key,
                    'value': criteria_row.required_value,
                    'is_required': bool(criteria_row.is_required),
                    'inclusion_keywords': criteria_row.inclusion_keywords,
                    'exclusion_keywords': criteria_row.exclusion_keywords
                })

            # Build response
            amount_display = None
            if scholarship_row.benefits_text:
                percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', scholarship_row.benefits_text)
                if percent_match and re.search(r'tuition', scholarship_row.benefits_text, re.IGNORECASE):
                    amount_display = f"{percent_match.group(1)}% tuition contribution"
            if amount_display is None and scholarship_row.amount is not None:
                if 0 < scholarship_row.amount < 1:
                    percent_value = scholarship_row.amount * 100
                    amount_display = f"{percent_value:.0f}% tuition contribution"
            scholarship_detail = {
                'id': scholarship_row.id,
                'title': scholarship_row.title,
                'description': scholarship_row.description,
                'amount': float(scholarship_row.amount) if scholarship_row.amount else None,
                'amount_display': amount_display,
                'benefits_text': scholarship_row.benefits_text,
                'deadline': scholarship_row.deadline.isoformat() if scholarship_row.deadline else None,
                'application_url': scholarship_row.application_url,
                'industry': scholarship_row.industry,
                'status': scholarship_row.status,
                'created_at': scholarship_row.created_at.isoformat() if scholarship_row.created_at else None,
                'organization': {
                    'id': scholarship_row.organization_id,
                    'name': scholarship_row.organization_name,
                    'type': scholarship_row.organization_type,
                    'website': scholarship_row.organization_website,
                    'jurisdiction_state': scholarship_row.jurisdiction_state,
                    'jurisdiction_country': scholarship_row.jurisdiction_country
                },
                'eligibility_criteria': eligibility_criteria
            }

            return jsonify(scholarship_detail), 200

    except Exception as e:
        logging.error(f"Error in get_scholarship_detail: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@bp_detail.route('/api/scholarships', methods=['POST'])
def create_scholarship():
    '''Adds new scholarship to database with eligibility criteria'''
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Input validation
        required_fields = ['title', 'description', 'organization_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate organization exists
        with engine.connect() as conn:
            org_check_query = text('SELECT id FROM organizations WHERE id = :org_id')
            org_result = conn.execute(org_check_query, {'org_id': data['organization_id']})

            if not org_result.first():
                return jsonify({'error': 'Organization not found'}), 400

        # Validate amount if provided
        amount = data.get('amount')
        if amount is not None:
            try:
                amount = float(amount)
                if amount < 0:
                    return jsonify({'error': 'Amount cannot be negative'}), 400
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid amount format'}), 400

        # Validate deadline if provided
        deadline = data.get('deadline')
        if deadline:
            try:
                datetime.strptime(deadline, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid deadline format. Use YYYY-MM-DD'}), 400

        # Validate status
        status = data.get('status', 'active')
        if status not in ['active', 'inactive', 'draft']:
            return jsonify({'error': 'Invalid status. Must be active, inactive, or draft'}), 400

        # Validate application_url if provided
        application_url = data.get('application_url', '').strip()
        if application_url and not (application_url.startswith('http://') or application_url.startswith('https://')):
            return jsonify({'error': 'Application URL must start with http:// or https://'}), 400

        jurisdiction_state = data.get('jurisdiction_state', '').strip()
        jurisdiction_country = data.get('jurisdiction_country', '').strip()
        if not jurisdiction_state:
            jurisdiction_state = data.get('offered_location', '').strip()
        industry = data.get('industry', '').strip()

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                if jurisdiction_state:
                    update_org_query = text('''
                        UPDATE organizations
                        SET jurisdiction_state = :jurisdiction_state
                        WHERE id = :organization_id
                    ''')
                    conn.execute(update_org_query, {
                        'jurisdiction_state': jurisdiction_state,
                        'organization_id': data['organization_id']
                    })

                if jurisdiction_country:
                    update_org_query = text('''
                        UPDATE organizations
                        SET jurisdiction_country = :jurisdiction_country
                        WHERE id = :organization_id
                    ''')
                    conn.execute(update_org_query, {
                        'jurisdiction_country': jurisdiction_country,
                        'organization_id': data['organization_id']
                    })

                # Insert scholarship
                eligibility_criteria = data.get('eligibility_criteria', [])
                legacy_location = data.get('eligible_location', '').strip()
                legacy_nationality = data.get('student_country_of_origin', '').strip()
                if not legacy_nationality:
                    legacy_nationality = data.get('student_origin_country', '').strip()
                if legacy_location:
                    eligibility_criteria.append({
                        'type': 'location',
                        'criteria_key': 'study_state',
                        'value': legacy_location
                    })
                if legacy_nationality:
                    eligibility_criteria.append({
                        'type': 'demographic',
                        'criteria_key': 'nationality',
                        'value': legacy_nationality.upper()
                    })

                eligibility_raw_text = data.get('eligibility_raw_text')
                if not eligibility_raw_text and eligibility_criteria:
                    eligibility_raw_text = json.dumps(eligibility_criteria, ensure_ascii=True)

                insert_scholarship_query = text('''
                    INSERT INTO scholarships 
                    (title, description, amount, deadline, organization_id, application_url, status, industry, eligibility_raw_text, created_at)
                    VALUES 
                    (:title, :description, :amount, :deadline, :organization_id, :application_url, :status, :industry, :eligibility_raw_text, NOW())
                ''')

                scholarship_params = {
                    'title': data['title'].strip(),
                    'description': data['description'].strip(),
                    'amount': amount,
                    'deadline': deadline if deadline else None,
                    'organization_id': data['organization_id'],
                    'application_url': application_url if application_url else None,
                    'status': status,
                    'industry': industry if industry else None,
                    'eligibility_raw_text': eligibility_raw_text
                }

                result = conn.execute(insert_scholarship_query, scholarship_params)
                scholarship_id = result.lastrowid

                # Insert eligibility criteria if provided
                if not eligibility_criteria:
                    eligibility_criteria.append({
                        'type': 'other',
                        'criteria_key': 'raw_text',
                        'value': 'Eligibility pending',
                        'is_required': True
                    })
                if eligibility_criteria:
                    for criteria in eligibility_criteria:
                        # Validate criteria
                        if not criteria.get('type') or not criteria.get('value'):
                            trans.rollback()
                            return jsonify({'error': 'Eligibility criteria must have type and value'}), 400

                        insert_criteria_query = text('''
                            INSERT INTO eligibility_criteria 
                            (scholarship_id, criteria_type, criteria_key, required_value, is_required,
                             inclusion_keywords, exclusion_keywords)
                            VALUES 
                            (:scholarship_id, :criteria_type, :criteria_key, :required_value, :is_required,
                             :inclusion_keywords, :exclusion_keywords)
                        ''')

                        criteria_type = normalize_criteria_type(
                            criteria.get('type'),
                            scholarship_id=scholarship_id,
                            source_url=application_url if application_url else None,
                            criteria=criteria
                        )
                        criteria_key = normalize_criteria_key(
                            criteria.get('criteria_key') or criteria.get('key')
                        )
                        if not criteria_key and criteria_type in {'location', 'demographic'}:
                            trans.rollback()
                            return jsonify({'error': 'Eligibility criteria must include criteria_key'}), 400
                        if not criteria_key:
                            criteria_key = normalize_criteria_key(criteria_type)
                        if not validate_criteria_key(criteria_type, criteria_key):
                            trans.rollback()
                            return jsonify({'error': f'Invalid criteria_key for {criteria_type}'}), 400
                        criteria_params = {
                            'scholarship_id': scholarship_id,
                            'criteria_type': criteria_type,
                            'criteria_key': criteria_key,
                            'required_value': criteria['value'].strip(),
                            'is_required': bool(criteria.get('is_required', True)),
                            'inclusion_keywords': criteria.get('inclusion_keywords'),
                            'exclusion_keywords': criteria.get('exclusion_keywords')
                        }

                        conn.execute(insert_criteria_query, criteria_params)

                trans.commit()

                return jsonify({
                    'message': 'Scholarship created successfully',
                    'scholarship_id': scholarship_id
                }), 201

            except Exception as e:
                trans.rollback()
                raise e

    except Exception as e:
        logging.error(f"Error in create_scholarship: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
