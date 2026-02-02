import logging

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from scholarship_search import bp_search
from scholarship_detail import bp_detail


def create_app():
    app = Flask(__name__)
    CORS(app)  # Enable CORS for frontend integration

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

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5001)
