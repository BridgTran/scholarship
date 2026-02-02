from datetime import datetime
import logging

from flask import Blueprint, request, jsonify
from sqlalchemy import text

from db import engine

bp_search = Blueprint('scholarship_search', __name__)


def parse_list_param(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(',') if item.strip()]


def add_criteria_filter(where_conditions, params, criteria_types, values, param_prefix, criteria_key=None):
    if not values:
        return
    clauses = []
    for index, value in enumerate(values):
        key = f"{param_prefix}_{index}"
        params[key] = f"%{value.lower()}%"
        clauses.append(f"LOWER(ec.required_value) LIKE :{key}")
    key_clause = ""
    if criteria_key:
        criteria_key_param = f"{param_prefix}_key"
        params[criteria_key_param] = criteria_key
        key_clause = f" AND ec.criteria_key = :{criteria_key_param}"
    types_clause = ', '.join([f"'{criteria_type}'" for criteria_type in criteria_types])
    where_conditions.append(
        "EXISTS ("
        "SELECT 1 FROM eligibility_criteria ec "
        "WHERE ec.scholarship_id = s.id "
        "AND ec.is_required = 1 "
        f"AND ec.criteria_type IN ({types_clause}) "
        f"{key_clause} "
        f"AND ({' OR '.join(clauses)})"
        ")"
    )


def add_in_filter(where_conditions, params, column, values, param_prefix):
    if not values:
        return
    keys = []
    for index, value in enumerate(values):
        key = f"{param_prefix}_{index}"
        params[key] = value.lower()
        keys.append(f":{key}")
    where_conditions.append(f"LOWER({column}) IN ({', '.join(keys)})")


@bp_search.route('/api/scholarships/search', methods=['GET'])
def search_scholarships():
    '''Returns filtered and sorted list of scholarships based on search criteria'''
    try:
        # Get query parameters
        search_term = request.args.get('q', '').strip()
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        organization_type = request.args.get('organization_type', '').strip()
        deadline_from = request.args.get('deadline_from', '').strip()
        deadline_to = request.args.get('deadline_to', '').strip()
        sort_by = request.args.get('sort_by', 'deadline')  # deadline, amount, title
        sort_order = request.args.get('sort_order', 'asc')  # asc, desc
        recently_closed = request.args.get('recently_closed', '').strip()
        gender = request.args.get('gender', '').strip()
        background_factors = request.args.get('background_factors', '').strip()
        age_group = request.args.get('age_group', '').strip()
        industries = request.args.get('industries', '').strip()
        social_impact = request.args.get('social_impact', '').strip()
        level_of_study = request.args.get('level_of_study', '').strip()
        citizenship_status = request.args.get('citizenship_status', '').strip()
        residency_status = request.args.get('residency_status', '').strip()
        nationality = request.args.get('nationality', '').strip()
        origin_region = request.args.get('origin_region', '').strip()
        study_state = request.args.get('study_state', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Max 100 per page

        # Input validation
        if page < 1:
            return jsonify({'error': 'Page must be >= 1'}), 400

        if per_page < 1:
            return jsonify({'error': 'Per page must be >= 1'}), 400

        if sort_by not in ['deadline', 'amount', 'title', 'created_at', 'industry']:
            sort_by = 'deadline'

        if sort_order not in ['asc', 'desc']:
            sort_order = 'asc'

        # Build WHERE clause dynamically
        if recently_closed:
            deadline_filter = "(s.deadline IS NULL OR s.deadline >= DATE_SUB(CURDATE(), INTERVAL 14 DAY))"
        else:
            deadline_filter = "(s.deadline IS NULL OR s.deadline >= CURDATE())"
        where_conditions = ["s.status = 'active'", deadline_filter]
        params = {}

        if search_term:
            where_conditions.append("(s.title LIKE :search_term OR s.description LIKE :search_term)")
            params['search_term'] = f'%{search_term}%'

        if min_amount is not None:
            where_conditions.append("s.amount >= :min_amount")
            params['min_amount'] = min_amount

        if max_amount is not None:
            where_conditions.append("s.amount <= :max_amount")
            params['max_amount'] = max_amount

        if organization_type:
            where_conditions.append("o.type = :organization_type")
            params['organization_type'] = organization_type

        if deadline_from:
            try:
                datetime.strptime(deadline_from, '%Y-%m-%d')
                where_conditions.append("s.deadline >= :deadline_from")
                params['deadline_from'] = deadline_from
            except ValueError:
                return jsonify({'error': 'Invalid deadline_from format. Use YYYY-MM-DD'}), 400

        if deadline_to:
            try:
                datetime.strptime(deadline_to, '%Y-%m-%d')
                where_conditions.append("s.deadline <= :deadline_to")
                params['deadline_to'] = deadline_to
            except ValueError:
                return jsonify({'error': 'Invalid deadline_to format. Use YYYY-MM-DD'}), 400

        if gender:
            add_criteria_filter(
                where_conditions,
                params,
                ['demographic', 'demographics'],
                parse_list_param(gender),
                'gender'
            )

        if background_factors:
            add_criteria_filter(
                where_conditions,
                params,
                ['demographic', 'demographics'],
                parse_list_param(background_factors),
                'background'
            )

        if age_group:
            add_criteria_filter(
                where_conditions,
                params,
                ['demographic', 'demographics'],
                parse_list_param(age_group),
                'age_group'
            )

        if industries:
            add_in_filter(
                where_conditions,
                params,
                's.industry',
                parse_list_param(industries),
                'industries'
            )

        if social_impact:
            add_criteria_filter(
                where_conditions,
                params,
                ['extracurricular', 'other'],
                parse_list_param(social_impact),
                'social_impact'
            )

        if level_of_study:
            add_criteria_filter(
                where_conditions,
                params,
                ['academic_level'],
                parse_list_param(level_of_study),
                'level_of_study'
            )

        if not residency_status and citizenship_status:
            residency_status = citizenship_status

        if residency_status:
            add_criteria_filter(
                where_conditions,
                params,
                ['demographic', 'demographics'],
                parse_list_param(residency_status),
                'residency_status',
                criteria_key='residency_status'
            )

        if nationality:
            add_criteria_filter(
                where_conditions,
                params,
                ['demographic', 'demographics'],
                parse_list_param(nationality),
                'nationality',
                criteria_key='nationality'
            )

        if origin_region:
            add_criteria_filter(
                where_conditions,
                params,
                ['demographic', 'demographics'],
                parse_list_param(origin_region),
                'origin_region',
                criteria_key='origin_region'
            )

        if study_state:
            add_criteria_filter(
                where_conditions,
                params,
                ['location'],
                parse_list_param(study_state),
                'study_state',
                criteria_key='study_state'
            )

        where_clause = ' AND '.join(where_conditions)

        # Build ORDER BY clause
        order_mapping = {
            'deadline': 's.deadline',
            'amount': 's.amount',
            'title': 's.title',
            'created_at': 's.created_at',
            'industry': 's.industry'
        }
        order_clause = f"{order_mapping[sort_by]} {sort_order.upper()}"

        # Calculate offset
        offset = (page - 1) * per_page
        params['limit'] = per_page
        params['offset'] = offset

        # Main query
        query = text(f'''
            SELECT 
                s.id,
                s.title,
                s.amount,
                s.deadline,
                s.industry,
                s.status,
                o.name as organization_name,
                o.type as organization_type,
                o.jurisdiction_state,
                o.jurisdiction_country
            FROM scholarships s
            JOIN organizations o ON s.organization_id = o.id
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT :limit OFFSET :offset
        ''')

        # Count query for pagination
        count_query = text(f'''
            SELECT COUNT(*) as total
            FROM scholarships s
            JOIN organizations o ON s.organization_id = o.id
            WHERE {where_clause}
        ''')

        with engine.connect() as conn:
            # Get results
            result = conn.execute(query, params)
            scholarships = []

            for row in result:
                amount_value = float(row.amount) if row.amount else None
                amount_display = None
                if amount_value is not None and 0 < amount_value < 1:
                    amount_display = f"{amount_value * 100:.0f}% tuition contribution"
                scholarships.append({
                    'id': row.id,
                    'title': row.title,
                    'amount': amount_value,
                    'amount_display': amount_display,
                    'deadline': row.deadline.isoformat() if row.deadline else None,
                    'industry': row.industry,
                    'jurisdiction_state': row.jurisdiction_state,
                    'jurisdiction_country': row.jurisdiction_country,
                    'organization_name': row.organization_name,
                    'organization_type': row.organization_type,
                    'status': row.status
                })

            # Get total count
            count_result = conn.execute(
                count_query,
                {k: v for k, v in params.items() if k not in ['limit', 'offset']}
            )
            total_count = count_result.scalar()

            # Calculate pagination info
            total_pages = (total_count + per_page - 1) // per_page

            return jsonify({
                'scholarships': scholarships,
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'total_items': total_count,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_prev': page > 1
                }
            }), 200

    except Exception as e:
        logging.error(f"Error in search_scholarships: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@bp_search.route('/api/scholarships/filter-options', methods=['GET'])
def get_filter_options():
    '''Provides available filter values for search interface'''
    try:
        with engine.connect() as conn:
            # Get organization types
            org_types_query = text('''
                SELECT DISTINCT type 
                FROM organizations 
                WHERE type IS NOT NULL AND type != ''
                ORDER BY type
            ''')
            org_types_result = conn.execute(org_types_query)
            organization_types = [row.type for row in org_types_result]

            # Get amount range
            amount_range_query = text('''
                SELECT 
                    MIN(amount) as min_amount,
                    MAX(amount) as max_amount
                FROM scholarships 
                WHERE status = 'active' AND amount IS NOT NULL
            ''')
            amount_result = conn.execute(amount_range_query)
            amount_row = amount_result.first()

            # Get upcoming deadlines for quick filters
            deadline_query = text('''
                SELECT DISTINCT deadline
                FROM scholarships 
                WHERE status = 'active' 
                AND deadline >= CURDATE()
                ORDER BY deadline
                LIMIT 10
            ''')
            deadline_result = conn.execute(deadline_query)
            upcoming_deadlines = [row.deadline.isoformat() for row in deadline_result]

            industries_query = text('''
                SELECT DISTINCT industry
                FROM scholarships
                WHERE industry IS NOT NULL AND industry != ''
                ORDER BY industry
            ''')
            industries_result = conn.execute(industries_query)
            industries = [row.industry for row in industries_result]
            default_industries = [
                'stem',
                'health',
                'business',
                'arts',
                'education',
                'law',
                'trades',
                'agriculture',
                'other'
            ]
            if industries:
                combined = {item.strip().lower() for item in industries if item}
                combined.update(default_industries)
                industries = sorted(combined)
            else:
                industries = default_industries

            gender_options = [
                'female',
                'male',
                'non-binary',
                'women',
                'men'
            ]
            background_factors_options = [
                'first-generation',
                'indigenous',
                'rural',
                'low-income',
                'disability'
            ]
            age_group_options = [
                'under-18',
                '18-24',
                '25-34',
                '35-plus',
                'mature-age'
            ]
            social_impact_options = [
                'community-service',
                'sustainability',
                'leadership',
                'volunteering'
            ]
            citizenship_status_options = [
                'citizen',
                'permanent-resident',
                'international',
                'temporary-visa'
            ]
            residency_status_options = [
                'citizen',
                'permanent-resident',
                'international',
                'temporary-visa'
            ]
            origin_region_options = [
                {'value': 'NORTH_ASIA', 'label': 'North Asia'},
                {'value': 'SOUTHEAST_ASIA', 'label': 'South East Asia'}
            ]
            sort_options = [
                {'value': 'deadline', 'label': 'Deadline (Soon to Late)'},
                {'value': 'amount_desc', 'label': 'Amount (High to Low)'},
                {'value': 'amount_asc', 'label': 'Amount (Low to High)'},
                {'value': 'title', 'label': 'Title (A to Z)'},
                {'value': 'industry', 'label': 'Industry (A to Z)'}
            ]
            amount_options = [
                {'value': '0-1000', 'label': '$0 - $1,000'},
                {'value': '1000-5000', 'label': '$1,000 - $5,000'},
                {'value': '5000-10000', 'label': '$5,000 - $10,000'},
                {'value': '10000-20000', 'label': '$10,000 - $20,000'},
                {'value': '20000+', 'label': '$20,000+'}
            ]
            deadline_options = [
                {'value': '7', 'label': 'Next 7 days'},
                {'value': '30', 'label': 'Next 30 days'},
                {'value': '90', 'label': 'Next 3 months'},
                {'value': '365', 'label': 'Next year'}
            ]

            return jsonify({
                'organization_types': organization_types,
                'level_of_study': [
                    'high-school-leaver',
                    'undergraduate',
                    'postgraduate',
                    'phd',
                    'vocational'
                ],
                'gender_options': gender_options,
                'background_factors_options': background_factors_options,
                'age_group_options': age_group_options,
                'social_impact_options': social_impact_options,
                'citizenship_status_options': citizenship_status_options,
                'residency_status_options': residency_status_options,
                'origin_region_options': origin_region_options,
                'sort_options': sort_options,
                'amount_options': amount_options,
                'deadline_options': deadline_options,
                'industries': industries,
                'amount_range': {
                    'min': float(amount_row.min_amount) if amount_row and amount_row.min_amount else 0,
                    'max': float(amount_row.max_amount) if amount_row and amount_row.max_amount else 0
                },
                'upcoming_deadlines': upcoming_deadlines
            }), 200

    except Exception as e:
        logging.error(f"Error in get_filter_options: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
