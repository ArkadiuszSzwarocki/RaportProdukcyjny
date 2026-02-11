"""Error handlers and logging configuration."""

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import render_template, flash, request


class NoiseFilter(logging.Filter):
    """Filter to suppress noisy 404/405 errors for known probe paths."""
    
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        
        # Suppress ERROR-level messages for known safe probe paths
        if record.levelno >= logging.ERROR and (
            ('404 Not Found' in msg or '405 Method Not Allowed' in msg)
        ):
            # Known noisy probes or static assets
            noisy_paths = ['/favicon.ico', '/.well-known/', '/.well-known/appspecific/', '/static/']
            for p in noisy_paths:
                if p in msg:
                    return False
        return True


def setup_logging(app):
    """Configure application logging with rotating file handlers.
    
    Sets up:
    - Main app logger to logs/app.log (10 MB, 5 backups)
    - Dedicated palety logger to logs/palety.log (2 MB, 3 backups)
    - Noise filter on both to suppress known harmless errors
    - Werkzeug logger attached to app handler
    
    Args:
        app: Flask application instance
    """
    logs_dir = os.path.join(os.path.dirname(app.root_path), 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Main app logger
    log_path = os.path.join(logs_dir, 'app.log')
    # Use delay=True so file is opened on first emit (reduces rotate race on Windows)
    handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8', delay=True)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s [pid=%(process)d]: %(message)s [in %(pathname)s:%(lineno)d]')
    handler.setFormatter(formatter)
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(handler)
    logging.getLogger('werkzeug').addHandler(handler)
    
    # Attach noise filter to reduce log spam
    noise_filter = NoiseFilter()
    handler.addFilter(noise_filter)
    logging.getLogger('werkzeug').addFilter(noise_filter)
    
    # Dedicated logger for palety (to avoid cluttering main log)
    palety_logger = logging.getLogger('palety_logger')
    palety_logger.setLevel(logging.INFO)
    palety_log_path = os.path.join(logs_dir, 'palety.log')
    palety_handler = RotatingFileHandler(palety_log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8', delay=True)
    palety_handler.setLevel(logging.INFO)
    palety_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    palety_handler.setFormatter(palety_formatter)
    if not palety_logger.handlers:
        palety_logger.addHandler(palety_handler)
    
    return handler, palety_logger


def register_error_handlers(app):
    """Register global error handlers for the Flask application.
    
    Args:
        app: Flask application instance
    """
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle uncaught exceptions with logging and user-friendly response."""
        try:
            error_msg = f"{error.__class__.__name__}: {str(error)}"
            app.logger.exception('Unhandled exception on %s %s: %s', request.method, request.path, error_msg)
            flash(f'❌ Błąd: {str(error)}', 'danger')
        except Exception as e:
            app.logger.exception('Error in error handler: %s', e)
        
        # Return 500 error page
        response = render_template('500.html')
        return response, 500

