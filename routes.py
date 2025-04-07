from flask import request, jsonify, Blueprint, render_template, session
from app import app, socketio, bot
from reddit import load_config, save_config
import logging
from venv import EnvBuilder

# Ensure praw is installed in the virtual environment
env_builder = EnvBuilder(with_pip=True)
env_builder.create('/path/to/your/venv')

# Activate the virtual environment
activate_this = '/path/to/your/venv/bin/activate_this.py'
exec(open(activate_this).read(), {'__file__': activate_this})

# Import praw
import praw
import json
from datetime import datetime, timedelta
import os
import threading

routes = Blueprint('routes', __name__)

@routes.route('/')
def index():
    return render_template('index.html')

@routes.route('/api/authenticate', methods=['POST'])
def authenticate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400

        # Validate required fields
        required_fields = ['username', 'password', 'client_id', 'client_secret']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400

        # Add user agent to data
        data['user_agent'] = 'RedditDMBot/1.0'

        # Authenticate with Reddit
        success = bot.authenticate(0)  # Use first bot slot

        if success:
            # Save bot configuration
            config = load_config()
            if 'bots' not in config:
                config['bots'] = []
            
            # Update or add bot configuration
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

            # Emit success event
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
            return jsonify({
                'status': 'error',
                'message': 'Authentication failed'
            }), 401

    except Exception as e:
        logging.error(f'Authentication error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Authentication failed',
            'error': str(e)
        }), 500

@routes.route('/api/set-target', methods=['POST'])
def set_target():
    try:
        data = request.get_json()
        if not data or 'subreddit' not in data:
            return jsonify({'status': 'error', 'message': 'No subreddit provided'}), 400

        subreddit = data['subreddit']
        success = bot.set_target_subreddit(subreddit)

        if success:
            # Update config
            config = load_config()
            config['target_subreddit'] = subreddit
            save_config(config)

            # Emit success event
            socketio.emit('bot_update', {
                'type': 'target_set',
                'data': {'subreddit': subreddit}
            })

            return jsonify({
                'status': 'success',
                'message': f'Target subreddit set to r/{subreddit}',
                'log': f'Target subreddit set to r/{subreddit}'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to set target subreddit'
            }), 400

    except Exception as e:
        logging.error(f'Set target error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to set target subreddit',
            'error': str(e)
        }), 500

@routes.route('/api/start', methods=['POST'])
def start_bot():
    try:
        success = bot.start()

        if success:
            # Update config
            config = load_config()
            config['running'] = True
            save_config(config)

            # Emit success event
            socketio.emit('bot_update', {
                'type': 'bot_started',
                'data': {'status': 'running'}
            })

            return jsonify({
                'status': 'success',
                'message': 'Bot started successfully',
                'log': 'Bot started successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to start bot'
            }), 400

    except Exception as e:
        logging.error(f'Start bot error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to start bot',
            'error': str(e)
        }), 500

@routes.route('/api/stop', methods=['POST'])
def stop_bot():
    try:
        success = bot.stop()

        if success:
            # Update config
            config = load_config()
            config['running'] = False
            save_config(config)

            # Emit success event
            socketio.emit('bot_update', {
                'type': 'bot_stopped',
                'data': {'status': 'stopped'}
            })

            return jsonify({
                'status': 'success',
                'message': 'Bot stopped successfully',
                'log': 'Bot stopped successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to stop bot'
            }), 400

    except Exception as e:
        logging.error(f'Stop bot error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to stop bot',
            'error': str(e)
        }), 500

@routes.route('/api/status', methods=['GET'])
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

        return jsonify({
            'status': 'success',
            'data': status
        })

    except Exception as e:
        logging.error(f'Get status error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to get bot status',
            'error': str(e)
        }), 500

@routes.route('/api/subreddit-info', methods=['POST'])
def get_subreddit_info():
    try:
        data = request.get_json()
        if not data or 'subreddit' not in data:
            return jsonify({'status': 'error', 'message': 'No subreddit provided'}), 400

        subreddit = data['subreddit']
        info = bot.get_subreddit_info(subreddit)

        if info:
            return jsonify({
                'status': 'success',
                'data': info
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to get subreddit info'
            }), 400

    except Exception as e:
        logging.error(f'Get subreddit info error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to get subreddit info',
            'error': str(e)
        }), 500

@routes.route('/api/update-dnd', methods=['POST'])
def update_dnd():
    try:
        data = request.get_json()
        if not data or 'usernames' not in data:
            return jsonify({'status': 'error', 'message': 'No usernames provided'}), 400

        usernames = data['usernames']
        success = bot.update_dnd_list(usernames)

        if success:
            # Update config
            config = load_config()
            config['dnd_list'] = usernames
            save_config(config)

            # Emit success event
            socketio.emit('bot_update', {
                'type': 'dnd_updated',
                'data': {'usernames': usernames}
            })

            return jsonify({
                'status': 'success',
                'message': 'DND list updated successfully',
                'log': f'DND list updated with {len(usernames)} usernames'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to update DND list'
            }), 400

    except Exception as e:
        logging.error(f'Update DND error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to update DND list',
            'error': str(e)
        }), 500

@routes.route('/api/bots', methods=['GET'])
def get_bots():
    try:
        config = load_config()
        return jsonify({
            'status': 'success',
            'data': config.get('bots', [])
        })

    except Exception as e:
        logging.error(f'Get bots error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to get bots',
            'error': str(e)
        }), 500

@routes.route('/api/bots/<int:index>', methods=['DELETE'])
def delete_bot(index):
    try:
        config = load_config()
        bots = config.get('bots', [])
        
        if 0 <= index < len(bots):
            # Remove bot
            bots.pop(index)
            config['bots'] = bots
            save_config(config)

            # Emit success event
            socketio.emit('bot_update', {
                'type': 'bot_deleted',
                'data': {'index': index}
            })

            return jsonify({
                'status': 'success',
                'message': 'Bot deleted successfully',
                'log': f'Bot at index {index} deleted successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Invalid bot index'
            }), 400

    except Exception as e:
        logging.error(f'Delete bot error: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to delete bot',
            'error': str(e)
        }), 500

# Error handlers
@routes.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'status': 'error',
        'message': 'Not found'
    }), 404

@routes.errorhandler(500)
def internal_error(error):
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500
