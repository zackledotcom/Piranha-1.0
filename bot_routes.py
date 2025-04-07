# --- bot_routes.py ---
from flask import Blueprint, request, jsonify
from app import socketio, bot
from reddit import load_config, save_config
import logging

bot_bp = Blueprint('bot', __name__)

@bot_bp.route('/api/start', methods=['POST'])
def start_bot():
    try:
        success = bot.start()
        if success:
            config = load_config()
            config['running'] = True
            save_config(config)
            socketio.emit('bot_update', {'type': 'bot_started', 'data': {'status': 'running'}})
            return jsonify({'status': 'success', 'message': 'Bot started successfully', 'log': 'Bot started successfully'})
        return jsonify({'status': 'error', 'message': 'Failed to start bot'}), 400
    except Exception as e:
        logging.error(f'Start bot error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to start bot', 'error': str(e)}), 500

@bot_bp.route('/api/stop', methods=['POST'])
def stop_bot():
    try:
        success = bot.stop()
        if success:
            config = load_config()
            config['running'] = False
            save_config(config)
            socketio.emit('bot_update', {'type': 'bot_stopped', 'data': {'status': 'stopped'}})
            return jsonify({'status': 'success', 'message': 'Bot stopped successfully', 'log': 'Bot stopped successfully'})
        return jsonify({'status': 'error', 'message': 'Failed to stop bot'}), 400
    except Exception as e:
        logging.error(f'Stop bot error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to stop bot', 'error': str(e)}), 500

@bot_bp.route('/api/status', methods=['GET'])
def get_status():
    try:
        config = load_config()
        status = {
            'authenticated': bot.is_authenticated(),
            'running': bot.is_running(),
            'target_subreddit': config.get('target_subreddit'),
            'messages_sent': bot.get_messages_sent(),
            'success_rate': bot.get_success_rate(),
            'active_bots': len([b for b in config.get('bots', []) if b.get('authenticated')]),
            'error_rate': bot.get_error_rate()
        }
        return jsonify({'status': 'success', 'data': status})
    except Exception as e:
        logging.error(f'Get status error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to get bot status', 'error': str(e)}), 500