"""Flask application factory."""

import os
import glob
from datetime import timedelta
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from scripts.raporty import format_godziny
from app.config import SECRET_KEY
from app.core.contexts import register_contexts
from app.core.daemon import start_daemon_threads
from app.core.error_handlers import setup_logging, register_error_handlers
from app.blueprints.admin import admin_bp
from app.blueprints.api import api_bp
from app.blueprints.planista import planista_bp
from app.blueprints.auth import auth_bp
from app.blueprints.quality import quality_bp
from app.blueprints.quality.magnet_cleaning import magnet_cleaning_bp
from app.blueprints.quality.separator_cleaning import separator_cleaning_bp
from app.blueprints.shifts import shifts_bp
from app.blueprints.panels import panels_bp
from app.blueprints.production import production_bp
from app.blueprints.warehouse import warehouse_bp
from app.blueprints.planning import planning_bp
from app.blueprints.journal import journal_bp
from app.blueprints.leaves import leaves_bp
from app.blueprints.overtime import overtime_bp
from app.blueprints.schedule import schedule_bp
from app.blueprints.recovery import recovery_bp
from app.blueprints.zarzad import zarzad_bp
from app.blueprints.compat import compat_bp
from app.blueprints.main import main_bp
from app.blueprints.struktura import struktura_bp
from app.blueprints.agro_warehouse import agro_warehouse_bp
from app.blueprints.mom import mom_bp
from app.blueprints.magazyny_nowe import magazyny_nowe_bp
from app.blueprints.scanner import scanner_bp
from app.blueprints.magazyn_dostawy import magazyn_dostawy_bp
from app.blueprints.traceability import traceability_bp
from app.blueprints.inwentaryzacja import inwentaryzacja_bp
from app.blueprints.inwentaryzacja_produkcji import inwentaryzacja_produkcji_bp
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
    # Create Flask app with explicit template folder path (absolute path from project root)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    template_folder = os.path.join(project_root, 'templates')
    static_folder = os.path.join(project_root, 'static')
    app = Flask(__name__, root_path=project_root, template_folder=template_folder, static_folder=static_folder)
    
    # Log template folder and available templates to help diagnose TemplateNotFound
    app.logger.debug('Flask template_folder=%s', template_folder)
    try:
        templates_list = glob.glob(os.path.join(template_folder, '**', '*.html'), recursive=True)
        for t in templates_list:
            app.logger.debug('Template file: %s', t)
    except Exception as e:
        app.logger.exception('Failed to enumerate templates: %s', e)
    
    # Configure with secret key – always load from environment first so
    # container restarts (Watchtower) do not invalidate existing session cookies.
    _secret_key = config_secret_key or os.environ.get('SECRET_KEY') or SECRET_KEY
    app.secret_key = _secret_key

    # Configure session to ensure cookies are properly set
    app.config['SESSION_COOKIE_SECURE'] = False  # Allow HTTP in development
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # Don't allow JS access
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cross-site requests
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_PERMANENT'] = True  # Make sessions survive app restarts

    # Load session timeout from env/config so middleware can read it from app.config
    from app.config import SESSION_TIMEOUT_MINUTES as _timeout_min
    app.config['SESSION_TIMEOUT_MINUTES'] = int(os.environ.get('SESSION_TIMEOUT_MINUTES', _timeout_min))
    
    # Set up logging and error handlers BEFORE any routes or blueprints
    setup_logging(app)
    register_error_handlers(app)
    
    # Add Jinja2 extensions
    app.jinja_env.add_extension('jinja2.ext.do')
    
    # Disable Jinja2 caching in development to pick up template changes immediately
    app.jinja_env.cache = None
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    
    # Register middleware (request/response processing)
    register_middleware(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(quality_bp)
    app.register_blueprint(magnet_cleaning_bp)
    app.register_blueprint(separator_cleaning_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(panels_bp)
    app.register_blueprint(production_bp)
    app.register_blueprint(warehouse_bp)
    app.register_blueprint(planning_bp, url_prefix='/api')
    app.register_blueprint(journal_bp)
    app.register_blueprint(leaves_bp, url_prefix='/api')
    app.register_blueprint(overtime_bp, url_prefix='/api')
    app.register_blueprint(schedule_bp)
    app.register_blueprint(recovery_bp, url_prefix='/api')
    app.register_blueprint(admin_bp)
    app.register_blueprint(compat_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(planista_bp)
    app.register_blueprint(zarzad_bp)
    app.register_blueprint(struktura_bp)
    app.register_blueprint(agro_warehouse_bp)
    app.register_blueprint(mom_bp)
    app.register_blueprint(magazyny_nowe_bp)
    app.register_blueprint(scanner_bp)
    app.register_blueprint(magazyn_dostawy_bp)
    app.register_blueprint(traceability_bp)
    app.register_blueprint(inwentaryzacja_bp)
    app.register_blueprint(inwentaryzacja_produkcji_bp)

    # Register debug routes if in debug mode
    register_debug_routes(app)
    
    # Register Jinja2 filters
    app.jinja_env.filters['format_czasu'] = format_godziny
    
    # Register context processors (inject helpers into templates)
    register_contexts(app)
    
    # Start background daemon threads (skip when running under pytest to avoid
    # background DB connections during test collection)
    if 'PYTEST_CURRENT_TEST' not in os.environ:
        # Detect if we are in the parent process of Flask's Werkzeug reloader (app.py debug run)
        # to avoid starting background threads twice (once in parent, once in child worker).
        import sys
        main_script = sys.argv[0] if (sys.argv and sys.argv[0]) else ''
        
        # Check if reloader is enabled via environment variable
        reloader_enabled = os.environ.get('FLASK_USE_RELOADER') == 'true' or os.environ.get('RELOADER_ENABLED') == 'true'
        
        is_reloader_parent = (
            (reloader_enabled or main_script.endswith('app.py') or 'app.py' in main_script)
            and os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
        )
        
        if is_reloader_parent:
            app.logger.info('Skipping start_daemon_threads() in Werkzeug reloader parent process (WERKZEUG_RUN_MAIN=%s)', os.environ.get('WERKZEUG_RUN_MAIN'))
        else:
            app.logger.info('Starting start_daemon_threads() in Flask process (WERKZEUG_RUN_MAIN=%s, reloader_enabled=%s)', os.environ.get('WERKZEUG_RUN_MAIN'), reloader_enabled)
            start_daemon_threads(app, cleanup_enabled=True)
    else:
        app.logger.debug('Skipping start_daemon_threads() under pytest')
    
    # Initialize database (skip during pytest to allow monkeypatching)
    if init_db:
        try:
            # Check if we're running under pytest
            if 'PYTEST_CURRENT_TEST' not in os.environ:
                db.setup_database()
            else:
                app.logger.debug('Skipping setup_database() under pytest')
        except Exception as e:
            app.logger.exception('setup_database() failed or skipped: %s', e)
    
    # Poinstruowanie aplikacji, aby czytała oryginalne nagłówki przekazane przez Nginxa:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    return app


def register_debug_routes(app):
    """Register temporary debug routes (only enabled when app.debug is True)."""
    # Intentionally register for local debugging regardless of app.debug so
    # devs can inspect routing while app.run may toggle debug later.

    @app.route('/__debug/url_map')
    def debug_url_map():
        rules = []
        for r in app.url_map.iter_rules():
            rules.append({'rule': str(r.rule), 'endpoint': r.endpoint, 'methods': sorted(list(r.methods))})
        return {'rules': rules}



    # Temporary debug endpoints can be registered below when running locally.


