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
    # Dedicated error logger
    # ------------------------------------------------------------------
    if not use_stream:
        error_log_path = os.path.join(logs_dir, 'error.log')
        error_handler = TimedRotatingFileHandler(
            error_log_path, when='midnight', interval=1, backupCount=30, encoding='utf-8', delay=True
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        error_handler.setFormatter(error_formatter)
        app.logger.addHandler(error_handler)

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

    # ------------------------------------------------------------------
    # Status changes logger — dedicated file for plan status diagnostics
    # ------------------------------------------------------------------
    status_logger = logging.getLogger('status_changes')
    status_logger.setLevel(logging.INFO)
    status_log_path = os.path.join(logs_dir, 'status_changes.log')
    status_handler = TimedRotatingFileHandler(
        status_log_path, when='midnight', interval=1, backupCount=60, encoding='utf-8', delay=True
    )
    status_handler.setLevel(logging.INFO)
    status_formatter = logging.Formatter('%(asctime)s STATUS: %(message)s')
    status_handler.setFormatter(status_formatter)
    # Avoid duplicate handlers on repeated app create
    if not status_logger.handlers:
        status_logger.addHandler(status_handler)

    # ------------------------------------------------------------------
    # Frontend errors logger — dedicated file for JS problems from browser
    # ------------------------------------------------------------------
    frontend_logger = logging.getLogger('frontend_errors')
    frontend_logger.setLevel(logging.ERROR)
    frontend_log_path = os.path.join(logs_dir, 'frontend_errors.log')
    frontend_handler = TimedRotatingFileHandler(
        frontend_log_path, when='midnight', interval=1, backupCount=30, encoding='utf-8', delay=True
    )
    frontend_handler.setLevel(logging.ERROR)
    frontend_formatter = logging.Formatter('%(asctime)s FRONTEND ERROR: %(message)s')
    frontend_handler.setFormatter(frontend_formatter)
    if not frontend_logger.handlers:
        frontend_logger.addHandler(frontend_handler)

    # ------------------------------------------------------------------
    # DATABASE Monitoring (Trap)
    # ------------------------------------------------------------------
    db_logger = logging.getLogger('db_errors')
    db_logger.setLevel(logging.ERROR)
    db_log_path = os.path.join(logs_dir, 'db_errors.log')
    db_handler = TimedRotatingFileHandler(
        db_log_path, when='midnight', interval=1, backupCount=30, encoding='utf-8', delay=True
    )
    db_handler.setLevel(logging.ERROR)
    db_formatter = logging.Formatter('%(asctime)s DB ERROR: %(message)s')
    db_handler.setFormatter(db_formatter)
    if not db_logger.handlers:
        db_logger.addHandler(db_handler)

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
            # Gather context for precise identification
            error_msg = f"{error.__class__.__name__}: {str(error)}"
            path = request.path
            
            # Determine "Action" - common keys for buttons in forms
            action = "N/A"
            if request.method == 'POST':
                # Check for common action triggers
                action = request.form.get('action') or request.form.get('submit') or "Unknown Action"
                # If it's a specific button like "confirm", "delete", etc.
                possible_actions = ['confirm', 'delete', 'update', 'save', 'add', 'przenies']
                for a in possible_actions:
                    if a in request.form:
                        action = f"Button: {a}"
                        break
            
            # Log structured header for easier parsing in Error Trap view
            app.logger.error(f"[TRAP_HEADER] URL: {path} | ACTION: {action}")
            app.logger.exception('Unhandled exception on %s %s: %s', request.method, request.path, error_msg)
            
            flash(f'❌ Błąd: {str(error)}', 'danger')
        except Exception as e:
            app.logger.exception('Error in error handler: %s', e)
        
        # Return 500 error page
        response = render_template('500.html')
        return response, 500

