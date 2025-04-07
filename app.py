from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import os
import json
import logging
from datetime import datetime
import threading
import sys
sys.path.append('..')
from bot import EvilRedditBot
import praw

app = Flask(__name__)

# Load the secret key from the configuration file
def load_secret_key():
    config_path = 'config/config.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get('secret_key', 'default_secret_key')  # Provide a fallback for development
    except FileNotFoundError:
        # Create a default config file with a hardcoded secret key
        default_config = {
            "secret_key": "default_secret_key",  # Replace with a secure key
            "reddit": {},
            "subreddits": [],
            "bot_actions": {
                "upvote": True,
                "comment": True,
                "response_message": ""
            },
            "ui": {
                "do_not_disturb": []
            }
        }
        os.makedirs('config', exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        logger.info("Created default configuration file with a secret key")
        return default_config["secret_key"]
    except Exception as e:
        logger.error(f"Error loading secret key: {str(e)}")
        raise

# Set the secret key for the Flask app
app.secret_key = load_secret_key()

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize bot
bot = EvilRedditBot()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('web_dashboard')

# Load config
def load_config():
    config_path = 'config/config.json'
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        default_config = {
            "reddit": {},
            "subreddits": [],
            "bot_actions": {
                "upvote": True,
                "comment": True,
                "response_message": ""
            },
            "ui": {
                "do_not_disturb": []
            }
        }
        os.makedirs('config', exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        logger.info("Created default configuration file")
        return default_config
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
        raise

# Save config
def save_config(config):
    try:
        os.makedirs('config', exist_ok=True)
        with open('config/config.json', 'w') as f:
            json.dump(config, f, indent=4)
        logger.info("Configuration saved successfully")
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")
        raise

# Evil logger
def log_action(action, status="SUCCESS", details=""):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {action} - {status}: {details}"
    logger.info(log_entry)
    return log_entry

@app.errorhandler(404)
def not_found(error):
    logger.error(f"404 error: {str(error)}")
    return jsonify({
        'status': 'error',
        'message': 'Resource not found',
        'log': log_action("Not Found", "ERROR", str(error))
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}")
    return jsonify({
        'status': 'error',
        'message': 'An internal error occurred',
        'log': log_action("Internal Error", "ERROR", str(error))
    }), 500

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

if __name__ == '__main__':
    # Load initial config
    load_config()
    
    # Register routes
    import routes
    app.register_blueprint(routes.routes)
    
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)