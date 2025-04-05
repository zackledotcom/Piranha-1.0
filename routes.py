from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
import json

routes_bp = Blueprint('routes', __name__)

@routes_bp.route('/')
def index():
    return render_template('index.html')

@routes_bp.route('/api/config', methods=['GET'])
def get_config():
    try:
        with open("config/config.json") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@routes_bp.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': 
datetime.utcnow().isoformat()})

@routes_bp.route('/api/authenticate', methods=['POST'])
def auth():
    data = request.json
    if not all(k in data for k in ['username', 'password', 'client_id', 
'client_secret']):
        return jsonify({'status': 'error', 'message': 'Missing 
credentials'}), 400
    return jsonify({'status': 'success', 'message': 'Authenticated 
(simulated)'})

