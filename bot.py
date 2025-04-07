import praw
import json
import time
import logging
from datetime import datetime, timedelta
import random
import openai
from typing import Dict, List, Optional, Any
from cryptography.fernet import Fernet
import backoff
import pytz
from tenacity import retry, stop_after_attempt, wait_exponential
import os
import pickle
from pathlib import Path
import threading
import prawcore

def load_config():
    """Load configuration from config.json file."""
    config_path = Path(__file__).parent / 'config' / 'config.json'
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading config: {str(e)}")
        return {}

class EvilRedditBot:
    def __init__(self):
        self.config = load_config()
        self.running = False
        self.current_subreddit = None
        self.activity_log = []
        self.reddit = None
        self.bots = []
        self.logger = logging.getLogger('EvilRedditBot')
        
        # Personality templates for different response styles
        self.personality_templates = {
            'friendly': {
                'greetings': ['Hey there!', 'Hi!', 'Hello!', 'Hey!'],
                'transition_phrases': ['Thanks for reaching out!', 'I appreciate your message!', 'Thanks for sharing!'],
                'closings': ['Have a great day!', 'Take care!', 'Cheers!', 'Best regards!']
            },
            'professional': {
                'greetings': ['Hello', 'Good day', 'Greetings'],
                'transition_phrases': ['Thank you for your message.', 'I appreciate your communication.', 'Thank you for reaching out.'],
                'closings': ['Best regards', 'Sincerely', 'Thank you for your time']
            },
            'casual': {
                'greetings': ['Yo!', 'Hey!', 'Hi there!', 'Hey hey!'],
                'transition_phrases': ['Thanks for the message!', 'Got your message!', 'Thanks for reaching out!'],
                'closings': ['Later!', 'See ya!', 'Take it easy!', 'Peace!']
            }
        }
        
        # Personality prompts for AI responses
        self.personality_prompts = {
            'friendly': "You are a friendly and approachable Reddit user. Keep responses casual and engaging.",
            'professional': "You are a professional and courteous Reddit user. Keep responses formal and helpful.",
            'casual': "You are a casual and laid-back Reddit user. Keep responses informal and fun."
        }
        
        self.rate_limits = {
            'messages_per_hour': 30,
            'messages_per_day': 100,
            'min_delay_between_messages': 60,
            'max_messages_per_user': 3,
            'max_retries': 3,
            'retry_delay': 5
        }
        self.message_history = {
            'hourly': {},
            'daily': {},
            'user_messages': {}
        }
        self.last_message_time = 0
        self.circuit_breaker = {
            'failures': 0,
            'last_failure': None,
            'threshold': 5,
            'reset_time': 300  # 5 minutes
        }
        
        # Initialize encryption
        self.encryption_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.encryption_key)
        
        # Initialize OpenAI with encrypted key
        if self.config.get('openai_api_key'):
            decrypted_key = self._decrypt_api_key(self.config['openai_api_key'])
            openai.api_key = decrypted_key
            
        # Initialize monitoring metrics
        self.metrics = {
            'total_messages': 0,
            'successful_messages': 0,
            'failed_messages': 0,
            'ai_responses': 0,
            'template_responses': 0,
            'last_health_check': None,
            'health_status': 'unknown'
        }
        
        # Create data directory if it doesn't exist
        self.data_dir = Path('data')
        self.data_dir.mkdir(exist_ok=True)
        
        # Load saved state if exists
        self.load_state()

    def _encrypt_api_key(self, api_key: str) -> str:
        """Encrypt API key before storing."""
        return self.cipher_suite.encrypt(api_key.encode()).decode()

    def _decrypt_api_key(self, encrypted_key: str) -> str:
        """Decrypt API key when needed."""
        return self.cipher_suite.decrypt(encrypted_key.encode()).decode()

    def generate_response(self, bot_config: Dict, message: str) -> str:
        """Generate a response using either AI or template-based system."""
        try:
            # Check if AI is enabled for this bot
            if bot_config.get('ai_enabled') and bot_config.get('ai_settings'):
                return self._generate_ai_response(bot_config, message)
            else:
                return self._generate_template_response(bot_config, message)
                
        except Exception as e:
            self.log_activity(f"Error generating response: {str(e)}", 'error')
            return "Hey! Thanks for your message. I'll get back to you soon!"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _generate_ai_response(self, bot_config: Dict, message: str) -> str:
        """Generate a response using OpenAI with retry logic."""
        try:
            ai_settings = bot_config['ai_settings']
            style = ai_settings.get('response_style', 'friendly')
            prompt = self.personality_prompts.get(style, self.personality_prompts['friendly'])
            
            # Add random delay to simulate typing
            time.sleep(random.uniform(1, 3))
            
            # Decrypt API key if needed
            if 'api_key' in ai_settings:
                api_key = self._decrypt_api_key(ai_settings['api_key'])
                openai.api_key = api_key
            
            # Generate response using OpenAI with error handling
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"Respond to this Reddit message: {message}"}
                    ],
                    max_tokens=150,
                    temperature=0.7,
                    presence_penalty=0.6,
                    frequency_penalty=0.6
                )
                
                generated_response = response.choices[0].message.content.strip()
                
                # Add occasional punctuation inconsistencies
                if random.random() < 0.2:
                    generated_response = generated_response.replace('!', random.choice(['!', '..', '...', '!?', '?!']))
                    generated_response = generated_response.replace('?', random.choice(['?', '??', '?!', '!?']))
                
                return generated_response
                
            except openai.error.RateLimitError:
                self.log_activity("OpenAI rate limit reached, falling back to template", 'warning')
                return self._generate_template_response(bot_config, message)
                
        except Exception as e:
            self.log_activity(f"Error generating AI response: {str(e)}", 'error')
            return self._generate_template_response(bot_config, message)

    def _generate_template_response(self, bot_config: Dict, message: str) -> str:
        """Generate a response using the template system."""
        personality = bot_config.get('personality', {})
        style = personality.get('response_style', 'friendly')
        templates = self.personality_templates.get(style, self.personality_templates['friendly'])
        
        # Add random delay to simulate typing
        time.sleep(random.uniform(1, 3))
        
        # Generate response components
        greeting = random.choice(templates['greetings'])
        transition = random.choice(templates['transition_phrases'])
        closing = random.choice(templates['closings'])
        
        # Add natural language variations
        response_parts = [
            greeting,
            self._add_natural_variations(message),
            transition,
            self._generate_contextual_response(message),
            closing
        ]
        
        return ' '.join(response_parts)

    def send_message(self, bot_index: int, recipient: str, message: str) -> bool:
        """Send a message with enhanced error handling and recovery."""
        try:
            # Check rate limits first
            if not self.check_rate_limits(recipient):
                return False

            bot = self.bots[bot_index]
            if not bot:
                return False

            # Generate natural response using AI
            response = self.generate_response(self.config['bots'][bot_index], message)
            
            # Add random typing delay
            time.sleep(random.uniform(0.5, 2))
            
            # Send message with retry logic
            for attempt in range(self.rate_limits['max_retries']):
                try:
                    self.reddit.redditor(recipient).message(response)
                    self.update_message_history(recipient)
                    self.log_activity(f"Message sent to {recipient}")
                    return True
                except Exception as e:
                    if attempt < self.rate_limits['max_retries'] - 1:
                        wait_time = self.rate_limits['retry_delay'] * (2 ** attempt)
                        self.log_activity(f"Retry {attempt + 1}/{self.rate_limits['max_retries']} after {wait_time}s", 'warning')
                        time.sleep(wait_time)
                    else:
                        self.circuit_breaker['failures'] += 1
                        self.circuit_breaker['last_failure'] = time.time()
                        self.log_activity(f"Error sending message after {self.rate_limits['max_retries']} attempts: {str(e)}", 'error')
                        return False
                
        except Exception as e:
            self.log_activity(f"Error in send_message: {str(e)}", 'error')
            return False

    def authenticate(self, bot_index=0):
        """Authenticate with Reddit using PRAW"""
        try:
            bot_config = self.config['bots'][bot_index]
            if not all(key in bot_config for key in ['username', 'password', 'client_id', 'client_secret', 'user_agent']):
                self.logger.error("Missing required Reddit credentials")
                return False

            self.reddit = praw.Reddit(
                username=bot_config['username'],
                password=bot_config['password'],
                client_id=bot_config['client_id'],
                client_secret=bot_config['client_secret'],
                user_agent=bot_config['user_agent']
            )
            self.logger.info(f"Authenticated as {bot_config['username']}")
            return True
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            return False

    def add_bot(self, bot_config):
        """Add a new bot configuration"""
        if len(self.config['bots']) >= 3:
            raise ValueError("Maximum number of bots (3) reached")
        
        self.config['bots'].append(bot_config)
        return len(self.config['bots']) - 1

    def remove_bot(self, bot_index):
        """Remove a bot configuration"""
        if 0 <= bot_index < len(self.config['bots']):
            self.config['bots'].pop(bot_index)
            return True
        return False

    def get_bot_status(self, bot_index):
        """Get the status of a specific bot"""
        if 0 <= bot_index < len(self.config['bots']):
            bot = self.config['bots'][bot_index]
            status = {
                'username': bot['username'],
                'authenticated': self.is_authenticated() and self.reddit.user.me().name == bot['username'],
                'subreddit': bot['subreddit'],
                'personality': bot['personality']
            }
            
            # Add avatar URL if authenticated
            if status['authenticated']:
                try:
                    user = self.reddit.user.me()
                    status['avatar_url'] = user.icon_img if hasattr(user, 'icon_img') else None
                except Exception as e:
                    self.logger.error(f"Error fetching avatar: {str(e)}")
                    status['avatar_url'] = None
            
            return status
        return None

    def is_authenticated(self):
        """Check if the bot is authenticated with Reddit"""
        return self.reddit is not None and hasattr(self.reddit, 'user') and self.reddit.user.me() is not None

    def process_submission(self, submission):
        """Process a single Reddit submission"""
        try:
            if not submission.author:
                self.logger.warning(f"Skipping submission {submission.id} - no author")
                return

            # Check if author is in protected users list
            if submission.author.name in self.config['bots'][0].get('protected_users', []):
                self.logger.info(f"Skipping protected user: {submission.author.name}")
                return

            actions = self.config['bots'][0]['actions']
            
            if actions.get('upvote', True):
                submission.upvote()
                self.logger.info(f"Upvoted submission: {submission.id} by {submission.author.name}")
            
            if actions.get('comment', True) and actions.get('response_message'):
                submission.reply(actions['response_message'])
                self.logger.info(f"Commented on submission: {submission.id}")
                
            # Add to activity log
            self.activity_log.append({
                'timestamp': datetime.now().isoformat(),
                'action': 'process_submission',
                'submission_id': submission.id,
                'author': submission.author.name,
                'success': True
            })
            
        except Exception as e:
            self.logger.error(f"Error processing submission {submission.id}: {str(e)}")
            self.activity_log.append({
                'timestamp': datetime.now().isoformat(),
                'action': 'process_submission',
                'submission_id': submission.id,
                'error': str(e),
                'success': False
            })

    def run(self):
        """Main bot loop with enhanced monitoring."""
        if not self.authenticate():
            self.logger.error("Failed to authenticate. Bot cannot start.")
            return False

        self.running = True
        self.current_subreddit = self.config['bots'][0]['subreddit']
        self.protected_users = self.config['bots'][0].get('protected_users', [])
        
        self.logger.info(f"Bot started monitoring r/{self.current_subreddit}")
        
        while self.running:
            try:
                # Perform health check
                if not self.check_health():
                    self.log_activity("Health check failed, waiting before retry", 'warning')
                    time.sleep(300)  # Wait 5 minutes before retry
                    continue
                
                # Monitor system health
                self.monitor_health()
                
                if not self.current_subreddit:
                    self.logger.warning("No subreddit specified. Waiting...")
                    time.sleep(60)
                    continue

                subreddit = self.reddit.subreddit(self.current_subreddit)
                for submission in subreddit.new(limit=5):
                    if not self.running:
                        break
                    self.process_submission(submission)
                
                # Save state periodically
                self.save_state()
                time.sleep(60)  # Wait before next batch
                
            except praw.exceptions.PRAWException as e:
                self.logger.error(f"PRAW error: {str(e)}")
                time.sleep(300)  # Wait longer on PRAW errors
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {str(e)}")
                if not self.running:  # Don't sleep if we're stopping
                    break
                time.sleep(60)

        self.logger.info("Bot stopped")
        return True

    def stop(self):
        """Stop the bot gracefully"""
        self.logger.info("Stopping bot...")
        self.running = False
        
    def get_status(self):
        """Get current bot status"""
        return {
            'running': self.running,
            'authenticated': self.is_authenticated(),
            'current_subreddit': self.current_subreddit,
            'protected_users_count': len(self.protected_users),
            'activity_log_count': len(self.activity_log)
        }

    def check_rate_limits(self, recipient):
        """Enhanced rate limiting with timezone awareness."""
        try:
            current_time = time.time()
            utc_now = datetime.now(pytz.UTC)
            
            # Check circuit breaker
            if self.circuit_breaker['failures'] >= self.circuit_breaker['threshold']:
                if current_time - self.circuit_breaker['last_failure'] < self.circuit_breaker['reset_time']:
                    self.log_activity("Circuit breaker active, waiting for reset", 'warning')
                    return False
                else:
                    self.circuit_breaker['failures'] = 0
            
            # Check hourly limit with timezone awareness
            hour_key = utc_now.strftime('%Y-%m-%d-%H')
            if hour_key not in self.message_history['hourly']:
                self.message_history['hourly'][hour_key] = 0
            if self.message_history['hourly'][hour_key] >= self.rate_limits['messages_per_hour']:
                self.log_activity("Hourly message limit reached", 'warning')
                return False
                
            # Check daily limit with timezone awareness
            day_key = utc_now.strftime('%Y-%m-%d')
            if day_key not in self.message_history['daily']:
                self.message_history['daily'][day_key] = 0
            if self.message_history['daily'][day_key] >= self.rate_limits['messages_per_day']:
                self.log_activity("Daily message limit reached", 'warning')
                return False
                
            # Check minimum delay between messages with jitter
            min_delay = self.rate_limits['min_delay_between_messages']
            jitter = random.uniform(-5, 5)
            if current_time - self.last_message_time < (min_delay + jitter):
                time.sleep(min_delay + jitter - (current_time - self.last_message_time))
                
            # Check user-specific limit with exponential backoff
            if recipient not in self.message_history['user_messages']:
                self.message_history['user_messages'][recipient] = {
                    'count': 0,
                    'last_reset': day_key,
                    'consecutive_failures': 0
                }
                
            user_history = self.message_history['user_messages'][recipient]
            if user_history['last_reset'] != day_key:
                user_history['count'] = 0
                user_history['last_reset'] = day_key
                user_history['consecutive_failures'] = 0
                
            if user_history['count'] >= self.rate_limits['max_messages_per_user']:
                backoff_time = min(300, 2 ** user_history['consecutive_failures'])
                self.log_activity(f"User message limit reached for {recipient}, backoff: {backoff_time}s", 'warning')
                time.sleep(backoff_time)
                return False
                
            return True
            
        except Exception as e:
            self.log_activity(f"Error in rate limiting: {str(e)}", 'error')
            return False

    def update_message_history(self, recipient):
        """Update message history after sending a message."""
        current_time = time.time()
        hour_key = datetime.now().strftime('%Y-%m-%d-%H')
        day_key = datetime.now().strftime('%Y-%m-%d')
        
        # Update hourly count
        self.message_history['hourly'][hour_key] = self.message_history['hourly'].get(hour_key, 0) + 1
        
        # Update daily count
        self.message_history['daily'][day_key] = self.message_history['daily'].get(day_key, 0) + 1
        
        # Update user-specific count
        if recipient not in self.message_history['user_messages']:
            self.message_history['user_messages'][recipient] = {
                'count': 0,
                'last_reset': day_key
            }
        self.message_history['user_messages'][recipient]['count'] += 1
        
        self.last_message_time = current_time

    def log_activity(self, message, level='info'):
        """Log activity with timestamp and level."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.activity_log.append({
            'timestamp': timestamp,
            'message': message,
            'level': level
        })
        # Keep only last 1000 logs
        if len(self.activity_log) > 1000:
            self.activity_log.pop(0)

    def cleanup_old_history(self):
        """Enhanced cleanup with timezone awareness."""
        try:
            utc_now = datetime.now(pytz.UTC)
            
            # Clean up hourly history (keep last 24 hours)
            self.message_history['hourly'] = {
                k: v for k, v in self.message_history['hourly'].items()
                if k >= (utc_now - timedelta(days=1)).strftime('%Y-%m-%d-%H')
            }
            
            # Clean up daily history (keep last 7 days)
            self.message_history['daily'] = {
                k: v for k, v in self.message_history['daily'].items()
                if k >= (utc_now - timedelta(days=7)).strftime('%Y-%m-%d')
            }
            
            # Clean up user message history with failure tracking
            day_key = utc_now.strftime('%Y-%m-%d')
            self.message_history['user_messages'] = {
                k: v for k, v in self.message_history['user_messages'].items()
                if v['last_reset'] >= day_key
            }
            
        except Exception as e:
            self.log_activity(f"Error in cleanup: {str(e)}", 'error')

    def save_state(self):
        """Save bot state to disk for recovery."""
        try:
            state = {
                'message_history': self.message_history,
                'circuit_breaker': self.circuit_breaker,
                'last_message_time': self.last_message_time,
                'metrics': self.metrics,
                'current_subreddit': self.current_subreddit,
                'protected_users': self.protected_users if hasattr(self, 'protected_users') else []
            }
            
            # Save state to file
            state_file = self.data_dir / 'bot_state.pkl'
            with open(state_file, 'wb') as f:
                pickle.dump(state, f)
                
            # Save activity log separately to prevent file from getting too large
            log_file = self.data_dir / 'activity_log.json'
            with open(log_file, 'w') as f:
                json.dump(self.activity_log[-1000:], f)
                
            self.log_activity("State saved successfully", 'info')
            
        except Exception as e:
            self.log_activity(f"Error saving state: {str(e)}", 'error')

    def load_state(self):
        """Load bot state from disk."""
        try:
            state_file = self.data_dir / 'bot_state.pkl'
            if state_file.exists():
                with open(state_file, 'rb') as f:
                    state = pickle.load(f)
                    
                self.message_history = state.get('message_history', self.message_history)
                self.circuit_breaker = state.get('circuit_breaker', self.circuit_breaker)
                self.last_message_time = state.get('last_message_time', 0)
                self.metrics = state.get('metrics', self.metrics)
                self.current_subreddit = state.get('current_subreddit')
                self.protected_users = state.get('protected_users', [])
                
                # Load activity log
                log_file = self.data_dir / 'activity_log.json'
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        self.activity_log = json.load(f)
                        
                self.log_activity("State loaded successfully", 'info')
                
        except Exception as e:
            self.log_activity(f"Error loading state: {str(e)}", 'error')

    def monitor_health(self):
        """Monitor system health and alert on issues."""
        try:
            current_time = time.time()
            
            # Calculate error rate
            recent_logs = [log for log in self.activity_log[-100:] if log['level'] in ['error', 'warning']]
            error_rate = len(recent_logs) / 100 if self.activity_log else 0
            
            # Update metrics
            self.metrics.update({
                'error_rate': error_rate,
                'success_rate': self.metrics['successful_messages'] / max(1, self.metrics['total_messages']),
                'circuit_breaker_status': self.circuit_breaker['failures'],
                'last_health_check': current_time
            })
            
            # Determine health status
            if error_rate > 0.2:
                self.metrics['health_status'] = 'critical'
                self.log_activity("Critical health status: High error rate detected", 'error')
            elif error_rate > 0.1:
                self.metrics['health_status'] = 'warning'
                self.log_activity("Warning health status: Elevated error rate", 'warning')
            else:
                self.metrics['health_status'] = 'healthy'
                
            # Save state periodically
            if current_time - self.last_message_time > 300:  # Every 5 minutes
                self.save_state()
                
        except Exception as e:
            self.log_activity(f"Error in health monitoring: {str(e)}", 'error')
            self.metrics['health_status'] = 'error'

    def check_health(self):
        """Perform health checks on all components."""
        try:
            checks = {
                'reddit_connection': self.is_authenticated(),
                'openai_connection': self.check_openai_connection(),
                'rate_limits': self.check_rate_limit_status(),
                'encryption': self.check_encryption_status(),
                'data_persistence': self.check_data_persistence()
            }
            
            # Log failed checks
            failed_checks = [check for check, status in checks.items() if not status]
            if failed_checks:
                self.log_activity(f"Health check failed for: {', '.join(failed_checks)}", 'error')
                
            return all(checks.values())
            
        except Exception as e:
            self.log_activity(f"Error in health check: {str(e)}", 'error')
            return False

    def check_openai_connection(self):
        """Check OpenAI API connection."""
        try:
            # Try a simple completion
            openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return True
        except Exception as e:
            self.log_activity(f"OpenAI connection check failed: {str(e)}", 'error')
            return False

    def check_rate_limit_status(self):
        """Check if rate limits are being respected."""
        try:
            current_time = time.time()
            utc_now = datetime.now(pytz.UTC)
            
            # Check hourly limits
            hour_key = utc_now.strftime('%Y-%m-%d-%H')
            hourly_count = self.message_history['hourly'].get(hour_key, 0)
            if hourly_count > self.rate_limits['messages_per_hour'] * 0.9:
                self.log_activity("Rate limit warning: Approaching hourly limit", 'warning')
                return False
                
            # Check daily limits
            day_key = utc_now.strftime('%Y-%m-%d')
            daily_count = self.message_history['daily'].get(day_key, 0)
            if daily_count > self.rate_limits['messages_per_day'] * 0.9:
                self.log_activity("Rate limit warning: Approaching daily limit", 'warning')
                return False
                
            return True
            
        except Exception as e:
            self.log_activity(f"Rate limit check failed: {str(e)}", 'error')
            return False

    def check_encryption_status(self):
        """Check if encryption is working properly."""
        try:
            test_key = "test_key"
            encrypted = self._encrypt_api_key(test_key)
            decrypted = self._decrypt_api_key(encrypted)
            return decrypted == test_key
        except Exception as e:
            self.log_activity(f"Encryption check failed: {str(e)}", 'error')
            return False

    def check_data_persistence(self):
        """Check if data persistence is working."""
        try:
            test_data = {'test': 'data'}
            test_file = self.data_dir / 'test.pkl'
            
            # Try to save
            with open(test_file, 'wb') as f:
                pickle.dump(test_data, f)
                
            # Try to load
            with open(test_file, 'rb') as f:
                loaded_data = pickle.load(f)
                
            # Clean up
            test_file.unlink()
            
            return loaded_data == test_data
            
        except Exception as e:
            self.log_activity(f"Data persistence check failed: {str(e)}", 'error')
            return False

    def get_subreddit_info(self, subreddit_name):
        try:
            if not self.reddit:
                self.reddit = praw.Reddit(
                    client_id=self.config['reddit']['client_id'],
                    client_secret=self.config['reddit']['client_secret'],
                    user_agent=self.config['reddit']['user_agent']
                )
            
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
            except praw.exceptions.RedditAPIException as e:
                if e.error_type == 'SUBREDDIT_NOEXIST':
                    raise Exception(f"Subreddit '{subreddit_name}' does not exist")
                raise
            
            # Get recent submissions for analysis
            recent_posts = list(subreddit.new(limit=10))
            
            # Calculate post frequency
            if recent_posts:
                time_diff = recent_posts[0].created_utc - recent_posts[-1].created_utc
                posts_per_day = len(recent_posts) / (time_diff / (24 * 60 * 60))
            else:
                posts_per_day = 0
            
            # Calculate engagement rate
            total_score = sum(post.score for post in recent_posts)
            total_comments = sum(post.num_comments for post in recent_posts)
            engagement_rate = ((total_score + total_comments) / len(recent_posts)) if recent_posts else 0
            
            # Get subreddit rules
            try:
                rules = [rule.short_name for rule in subreddit.rules]
            except Exception as e:
                self.logger.warning(f"Could not fetch subreddit rules: {str(e)}")
                rules = []
            
            # Get posting restrictions
            try:
                posting_restrictions = {
                    'allow_images': subreddit.allow_images,
                    'allow_videos': subreddit.allow_videos,
                    'spoilers_enabled': subreddit.spoilers_enabled
                }
            except Exception as e:
                self.logger.warning(f"Could not fetch posting restrictions: {str(e)}")
                posting_restrictions = None
            
            return {
                'name': subreddit_name,
                'subscribers': subreddit.subscribers,
                'active_users': subreddit.active_user_count,
                'post_frequency': f"{posts_per_day:.1f} posts/day",
                'engagement_rate': f"{engagement_rate:.1f}",
                'description': subreddit.public_description,
                'type': subreddit.subreddit_type,
                'sentiment': 'positive' if engagement_rate > 10 else 'neutral',
                'rules': rules,
                'posting_restrictions': posting_restrictions,
                'created_utc': subreddit.created_utc,
                'is_nsfw': subreddit.over18,
                'is_private': subreddit.subreddit_type == 'private'
            }
        except prawcore.exceptions.ResponseException as e:
            if e.response.status_code == 429:
                raise Exception("Rate limit exceeded. Please try again later.")
            raise
        except Exception as e:
            self.logger.error(f"Error getting subreddit info: {str(e)}")
            raise