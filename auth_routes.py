from flask import Blueprint, request, jsonify
from app import socketio, bot
from reddit import load_config, save_config
import logging

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/authenticate', methods=['POST'])
def authenticate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400

        required_fields = ['username', 'password', 'client_id', 'client_secret']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400

        data['user_agent'] = 'RedditDMBot/1.0'
        success = bot.authenticate(
            username=data['username'],
            password=data['password'],
            client_id=data['client_id'],
            client_secret=data['client_secret']
        )

        if success:
            config = load_config()
            if 'bots' not in config:
                config['bots'] = []

            bot_config = {
                'username': data['username'],
                'client_id': data['client_id'],
                'client_secret': data['client_secret'],
                'subreddit': data.get('subreddit'),
                'personality': {
                    'response_style': data.get('ai_settings', {}).get('response_style', 'friendly')
                },
                'ai_enabled': data.get('ai_enabled', False),
                'ai_settings': data.get('ai_settings'),
                'authenticated': True
            }

            if config['bots']:
                config['bots'][0] = bot_config
            else:
                config['bots'].append(bot_config)

            save_config(config)

            socketio.emit('bot_update', {
                'type': 'auth_success',
                'data': {'username': data['username']}
            })

            return jsonify({
                'status': 'success',
                'message': 'Bot authenticated successfully',
                'log': f'Bot {data["username"]} authenticated successfully'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Authentication failed'}), 401

    except Exception as e:
        logging.error(f'Authentication error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Authentication failed',
            'error': str(e)
        }), 500