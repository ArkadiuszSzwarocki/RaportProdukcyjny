#!/usr/bin/env python
"""Debug server runner with full logging and request monitoring."""

import os
import sys
import logging
from datetime import datetime

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Configure enhanced logging BEFORE importing Flask
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/debug.log', encoding='utf-8', mode='a')
    ]
)

logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("DEBUG SERVER STARTING - %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
logger.info("=" * 80)

# Import and create the app
from app.core.factory import create_app

# Create app with debug enabled
app = create_app()
app.config['DEBUG'] = True
app.config['TESTING'] = False
app.config['PROPAGATE_EXCEPTIONS'] = True

# Add request/response logging middleware
@app.before_request
def log_request():
    """Log every incoming request."""
    from flask import request
    logger.info(
        ">>> REQUEST: %s %s | IP: %s | User-Agent: %s",
        request.method,
        request.full_path,
        request.remote_addr,
        request.headers.get('User-Agent', 'Unknown')[:100]
    )
    if request.method in ['POST', 'PUT', 'PATCH']:
        try:
            logger.debug("   Request data: %s", str(request.get_data(as_text=True))[:500])
        except:
            pass

@app.after_request
def log_response(response):
    """Log every outgoing response."""
    from flask import request
    logger.info(
        "<<< RESPONSE: %s %s | Status: %d | Content-Type: %s",
        request.method,
        request.full_path,
        response.status_code,
        response.content_type
    )
    return response

@app.teardown_appcontext
def close_connection(exception):
    """Handle any exceptions and cleanup."""
    if exception:
        logger.error("EXCEPTION during request: %s", str(exception), exc_info=True)

logger.info("Starting Flask development server on http://localhost:5000")
logger.info("Press CTRL+C to stop")
logger.info("-" * 80)

if __name__ == '__main__':
    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True,
            use_debugger=True,
            use_reloader=True,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Server crashed: %s", e)
        sys.exit(1)
