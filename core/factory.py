"""Flask application factory."""

import os
from flask import Flask
from scripts.raporty import format_godziny
from config import SECRET_KEY
from core.contexts import register_contexts
from core.daemon import start_daemon_threads
from core.error_handlers import setup_logging, register_error_handlers
from routes_admin import admin_bp
from routes_api import api_bp
from routes_planista import planista_bp
from routes_auth import auth_bp
from routes_quality import quality_bp
from routes_shifts import shifts_bp
from routes_panels import panels_bp
from routes_production import production_bp
from routes_warehouse import warehouse_bp
import db


def create_app(config_secret_key=None, init_db=True):
    """Create and configure Flask application.
    
    Args:
        config_secret_key: Override SECRET_KEY from config (useful for testing)
        init_db: Whether to initialize the database (skip during pytest)
    
    Returns:
        Configured Flask application instance
    """
    # Create Flask app
    app = Flask(__name__)
    
    # Configure with secret key
    app.secret_key = config_secret_key or SECRET_KEY
    
    # Set up logging and error handlers BEFORE any routes or blueprints
    setup_logging(app)
    register_error_handlers(app)
    
    # Add Jinja2 extensions
    app.jinja_env.add_extension('jinja2.ext.do')
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(quality_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(panels_bp)
    app.register_blueprint(production_bp)
    app.register_blueprint(warehouse_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(planista_bp)
    
    # Register Jinja2 filters
    app.jinja_env.filters['format_czasu'] = format_godziny
    
    # Register context processors (inject helpers into templates)
    register_contexts(app)
    
    # Start background daemon threads
    start_daemon_threads(app, cleanup_enabled=False)
    
    # Initialize database (skip during pytest to allow monkeypatching)
    if init_db:
        try:
            # Check if we're running under pytest
            if 'PYTEST_CURRENT_TEST' not in os.environ:
                db.setup_database()
            else:
                app.logger.debug('Skipping setup_database() under pytest')
        except Exception:
            try:
                app.logger.exception('setup_database() failed or skipped')
            except Exception:
                pass
    
    return app
