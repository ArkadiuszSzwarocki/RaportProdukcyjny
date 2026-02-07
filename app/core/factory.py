"""Flask application factory."""

import os
from flask import Flask
from scripts.raporty import format_godziny
from app.config import SECRET_KEY
from app.core.contexts import register_contexts
from app.core.daemon import start_daemon_threads
from app.core.error_handlers import setup_logging, register_error_handlers
from app.blueprints.routes_admin import admin_bp
from app.blueprints.routes_api import api_bp
from app.blueprints.routes_planista import planista_bp
from app.blueprints.routes_auth import auth_bp
from app.blueprints.routes_quality import quality_bp
from app.blueprints.routes_shifts import shifts_bp
from app.blueprints.routes_panels import panels_bp
from app.blueprints.routes_production import production_bp
from app.blueprints.routes_warehouse import warehouse_bp
from app.blueprints.routes_planning import planning_bp
from app.blueprints.routes_journal import journal_bp
from app.blueprints.routes_leaves import leaves_bp
from app.blueprints.routes_schedule import schedule_bp
from app.blueprints.routes_testing import testing_bp
from app.blueprints.routes_recovery import recovery_bp
from app.blueprints.routes_zarzad import zarzad_bp
from app.blueprints.routes_compat import compat_bp
from app.blueprints.routes_main import main_bp
from app import db
from app.core.middleware import register_middleware


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
    
    # Register middleware (request/response processing)
    register_middleware(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(quality_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(panels_bp)
    app.register_blueprint(production_bp)
    app.register_blueprint(warehouse_bp)
    app.register_blueprint(planning_bp)
    app.register_blueprint(journal_bp)
    app.register_blueprint(leaves_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(testing_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(compat_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(planista_bp)
    app.register_blueprint(zarzad_bp)
    
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

