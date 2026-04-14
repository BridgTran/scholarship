import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

from scholarship_search import bp_search
from scholarship_detail import bp_detail

# Initialised here; bound to the app instance inside create_app() via init_app()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv('RATE_LIMIT', '60 per minute')],
    storage_uri=os.getenv('LIMITER_STORAGE_URI', 'memory://'),
)


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY')
    if not app.secret_key:
        raise RuntimeError('SECRET_KEY environment variable is not set')

    # CORS — restrict to allowed origins only
    allowed_origins = [o.strip() for o in os.getenv('CORS_ORIGINS', 'http://localhost:5001').split(',')]
    CORS(app, origins=allowed_origins)

    # Rate limiting — applies to all routes by default
    limiter.init_app(app)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Register blueprints
    app.register_blueprint(bp_search)
    app.register_blueprint(bp_detail)

    @app.route('/scholarship_search', endpoint='scholarship_search')
    def scholarship_search_page():
        return send_from_directory('static', 'scholarship_search.html')

    @app.route('/scholarship/<int:scholarship_id>', endpoint='scholarship_detail_page')
    def scholarship_detail_page(scholarship_id):
        return send_from_directory('static', 'scholarship_detail.html')

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({'error': 'Too many requests. Please slow down and try again shortly.'}), 429

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.getenv('FLASK_PORT', 5001))
    app.run(debug=debug, host='0.0.0.0', port=port)
