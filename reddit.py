import json
import os
from datetime import datetime

def load_config():
    """Load configuration from config file."""
    try:
        with open('web_dashboard/config/config.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "reddit": {},
            "bots": [{
                "subreddit": "",
                "protected_users": [],
                "actions": {
                    "upvote": True,
                    "comment": True,
                    "response_message": ""
                }
            }],
            "ui": {
                "do_not_disturb": []
            }
        }

def save_config(config):
    """Save configuration to config file."""
    os.makedirs('web_dashboard/config', exist_ok=True)
    with open('web_dashboard/config/config.json', 'w') as f:
        json.dump(config, f, indent=4)

def log_action(action, status="SUCCESS", details=""):
    """Log bot actions with timestamp."""
    os.makedirs('web_dashboard/logs', exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{status}] {action} - {details}\n"
    
    with open('web_dashboard/logs/bot.log', 'a') as f:
        f.write(log_entry)
    
    return log_entry.strip()