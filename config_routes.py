from flask import Blueprint, request, jsonify
from app import socketio, bot
from reddit import load_config, save_config
import logging

config_bp = Blueprint('config', __name__)

@config_bp.route('/api/set-target', methods=['POST'])
def set_target():
    try:
        data = request.get_json()
        if not data or 'subreddit' not in data:
            return jsonify({'status': 'error', 'message': 'No subreddit provided'}), 400
        subreddit = data['subreddit']
        success = bot.set_target_subreddit(subreddit)
        if success:
            config = load_config()
            config['target_subreddit'] = subreddit
            save_config(config)
            socketio.emit('bot_update', {'type': 'target_set', 'data': {'subreddit': subreddit}})
            return jsonify({'status': 'success', 'message': f'Target subreddit set to r/{subreddit}', 'log': f'Target subreddit set to r/{subreddit}'})
        return jsonify({'status': 'error', 'message': 'Failed to set target subreddit'}), 400
    except Exception as e:
        logging.error(f'Set target error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to set target subreddit', 'error': str(e)}), 500

@config_bp.route('/api/update-dnd', methods=['POST'])
def update_dnd():
    try:
        data = request.get_json()
        if not data or 'usernames' not in data:
            return jsonify({'status': 'error', 'message': 'No usernames provided'}), 400
        usernames = data['usernames']
        success = bot.update_dnd_list(usernames)
        if success:
            config = load_config()
            config['dnd_list'] = usernames
            save_config(config)
            socketio.emit('bot_update', {'type': 'dnd_updated', 'data': {'usernames': usernames}})
            return jsonify({'status': 'success', 'message': 'DND list updated successfully', 'log': f'DND list updated with {len(usernames)} usernames'})
        return jsonify({'status': 'error', 'message': 'Failed to update DND list'}), 400
    except Exception as e:
        logging.error(f'Update DND error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to update DND list', 'error': str(e)}), 500

@config_bp.route('/api/bots', methods=['GET'])
def get_bots():
    try:
        config = load_config()
        return jsonify({'status': 'success', 'data': config.get('bots', [])})
    except Exception as e:
        logging.error(f'Get bots error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to get bots', 'error': str(e)}), 500

@config_bp.route('/api/bots/<int:index>', methods=['DELETE'])
def delete_bot(index):
    try:
        config = load_config()
        bots = config.get('bots', [])
        if 0 <= index < len(bots):
            bots.pop(index)
            config['bots'] = bots
            save_config(config)
            socketio.emit('bot_update', {'type': 'bot_deleted', 'data': {'index': index}})
            return jsonify({'status': 'success', 'message': 'Bot deleted successfully', 'log': f'Bot at index {index} deleted successfully'})
        return jsonify({'status': 'error', 'message': 'Invalid bot index'}), 400
    except Exception as e:
        logging.error(f'Delete bot error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Failed to delete bot', 'error': str(e)}), 500