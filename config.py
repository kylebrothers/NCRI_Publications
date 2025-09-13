"""
Configuration and setup for the Promotion Letters Tool
"""

import os
import logging
import anthropic
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Simple configuration without external dependencies
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this')
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size
    
    return app

def setup_logging():
    """Configure application logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/app.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def setup_rate_limiter(app):
    """Configure rate limiting"""
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["100 per hour"]
    )
    return limiter

def setup_claude_client():
    """Initialize Claude API client"""
    try:
        client = anthropic.Anthropic(
            api_key=os.environ.get('CLAUDE_API_KEY')
        )
        return client
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to initialize Claude client: {e}")
        return None

def ensure_directories():
    """Create necessary directories"""
    os.makedirs('logs', exist_ok=True)
