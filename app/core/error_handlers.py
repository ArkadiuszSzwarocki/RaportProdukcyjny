"""Error handlers and logging configuration."""

import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
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
    - Main app logger → logs/app.log (INFO+, daily rotation, 30 days)
      DEBUG messages are kept for development but do NOT go to the file.
    - Dedicated audit logger → logs/audit.log (INFO+, daily, 90 days)
      Human-readable record of every user action (login, confirming pallets, etc.)
    - Dedicated palety logger → logs/palety.log (INFO+, daily, 30 days)
    - Noise filter on the main handler to suppress known harmless 404/405 probes.
    - Werkzeug HTTP access log is intentionally NOT piped to app.log; it goes to
      its own stderr / access stream to avoid cluttering the application log.

    Args:
        app: Flask application instance
    """
    # Get project root: app.root_path points to app/core, so go up 2 levels
    project_root = os.path.dirname(os.path.dirname(app.root_path))
    logs_dir = os.path.join(project_root, 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # ------------------------------------------------------------------
    # Main app logger (INFO level in production to eliminate debug noise)
    # ------------------------------------------------------------------
    # During pytest runs avoid writing to rotating files to prevent Windows
    # permission errors when pytest/other processes rotate logs concurrently.
    use_stream = 'PYTEST_CURRENT_TEST' in os.environ
    log_path = os.path.join(logs_dir, 'app.log')
    if use_stream:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s [pid=%(process)d]: %(message)s')
        handler.setFormatter(formatter)
        app.logger.setLevel(logging.DEBUG)
        # Avoid duplicate handlers in repeated create_app calls during tests
        if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
            app.logger.addHandler(handler)
        noise_filter = NoiseFilter()
        handler.addFilter(noise_filter)
    else:
        # Use time-based rotation: rotate daily and keep 30 days of logs
        # Use delay=True so file is opened on first emit (reduces rotate race on Windows)
        handler = TimedRotatingFileHandler(
            log_path, when='midnight', interval=1, backupCount=30, encoding='utf-8', delay=True
        )
        # INFO level: debug-trace messages stay out of the file log
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        app.logger.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        # Noise filter suppresses known harmless 404/405 probes
        noise_filter = NoiseFilter()
        handler.addFilter(noise_filter)
        # Do NOT attach werkzeug to the app handler — its HTTP access lines
        # (e.g. "GET /planista HTTP/1.1 200 –") are noise in app.log.
        # werkzeug writes to stderr by default which is fine.

    # ------------------------------------------------------------------
    # Audit logger — human-readable record of user actions
    # ------------------------------------------------------------------
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    # Don't propagate to root logger (avoids duplicate lines in app.log)
    audit_logger.propagate = False
    if not use_stream:
        audit_log_path = os.path.join(logs_dir, 'audit.log')
        audit_handler = TimedRotatingFileHandler(
            audit_log_path, when='midnight', interval=1, backupCount=90, encoding='utf-8', delay=True
        )
        audit_handler.setLevel(logging.INFO)
        audit_formatter = logging.Formatter('%(asctime)s AUDIT: %(message)s')
        audit_handler.setFormatter(audit_formatter)
        if not audit_logger.handlers:
            audit_logger.addHandler(audit_handler)
    else:
        # In tests: write audit to a stream handler so it is capturable
        if not audit_logger.handlers:
            audit_stream = logging.StreamHandler()
            audit_stream.setLevel(logging.INFO)
            audit_stream.setFormatter(logging.Formatter('%(asctime)s AUDIT: %(message)s'))
            audit_logger.addHandler(audit_stream)

    # ------------------------------------------------------------------
    # Dedicated palety logger (unchanged)
    # ------------------------------------------------------------------
    palety_logger = logging.getLogger('palety_logger')
    palety_logger.setLevel(logging.INFO)
    palety_log_path = os.path.join(logs_dir, 'palety.log')
    # Rotate palety log daily and keep 30 days
    palety_handler = TimedRotatingFileHandler(
        palety_log_path, when='midnight', interval=1, backupCount=30, encoding='utf-8', delay=True
    )
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

