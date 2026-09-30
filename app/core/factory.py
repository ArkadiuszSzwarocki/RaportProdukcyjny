"""Flask application factory."""

import os
from datetime import timedelta

from flask import Flask

from scripts.raporty import format_godziny
from app.config import SECRET_KEY
from app.core.admin_security_hardening import register_admin_security_hardening
from app.core.contexts import register_contexts
from app.core.daemon import start_daemon_threads
from app.core.error_handlers import setup_logging, register_error_handlers
from app.core.legacy_print_hardening import register_legacy_print_hardening
from app.core.runtime_security_hardening import register_runtime_security_hardening
from app.core.security_hardening import (
    apply_proxy_policy,
    register_legacy_secret_rejection,
    register_role_integrity_check,
)
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
from app.blueprints.warehouse_v2 import warehouse_v2_bp
from app.blueprints.scanner import scanner_bp
from app.blueprints.magazyn_dostawy import magazyn_dostawy_bp
from app.blueprints.traceability import traceability_bp
from app.blueprints.inwentaryzacja import inwentaryzacja_bp
from app.blueprints.inwentaryzacja_produkcji import inwentaryzacja_produkcji_bp
from app.blueprints.osip import osip_bp
from app.blueprints.maluchy import maluchy_bp
from app import db
from app.core.middleware import register_middleware


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _is_production():
    return (
        str(os.environ.get('FLASK_ENV', '')).strip().lower() == 'production'
        or str(os.environ.get('ENV', '')).strip().lower() == 'production'
    )


def _debug_routes_enabled():
    if _is_production():
        return False
    return _env_bool('ENABLE_DEBUG_ROUTES', False) or _env_bool('FLASK_DEBUG', False)


def _restore_fallback_config(app, project_root):
    cfg_dir = os.path.join(project_root, 'config')
    cfg_fallback = os.path.join(project_root, 'config_fallback')
    if not os.path.isdir(cfg_fallback):
        return
    os.makedirs(cfg_dir, exist_ok=True)
    for fname in os.listdir(cfg_fallback):
        dst = os.path.join(cfg_dir, fname)
        src = os.path.join(cfg_fallback, fname)
        if (not os.path.exists(dst) or os.path.getsize(dst) == 0) and os.path.isfile(src):
            try:
                import shutil
                shutil.copy2(src, dst)
                app.logger.info('Restored missing config file from fallback: %s', fname)
            except Exception as exc:
                app.logger.warning('Could not restore config file %s: %s', fname, exc)


def _configure_secret_key(app, config_secret_key=None):
    secret_key = config_secret_key or os.environ.get('SECRET_KEY') or SECRET_KEY
    insecure_keys = {
        'tajnyKluczAgronetzwerk',
        'dev-secret-key',
        'test-secret',
        'change-me-in-production',
        'your-secret-key-here-min-32-chars',
        'CHANGE_THIS_TO_RANDOM_SECRET_KEY_MIN_32_CHARACTERS',
    }

    if _is_production():
        if not secret_key or secret_key in insecure_keys or len(secret_key) < 32:
            raise RuntimeError(
                'CRITICAL SECURITY ERROR: Production requires a unique SECRET_KEY '
                'with at least 32 characters.'
            )
        from app.core.crypto_utils import _get_fernet_instance
        _get_fernet_instance()
    elif not secret_key or secret_key in insecure_keys:
        import secrets
        secret_key = secrets.token_hex(32)
        app.logger.warning(
            'SECURITY WARNING: generated a temporary SECRET_KEY for this development process.'
        )

    app.secret_key = secret_key


def _configure_sessions(app):
    cookie_secure_raw = os.environ.get('SESSION_COOKIE_SECURE')
    if cookie_secure_raw is not None:
        app.config['SESSION_COOKIE_SECURE'] = _env_bool('SESSION_COOKIE_SECURE')
    else:
        app.config['SESSION_COOKIE_SECURE'] = _env_bool('USE_SSL', False)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_PERMANENT'] = True
    app.config['MAX_CONTENT_LENGTH'] = int(
        os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
    )
    from app.config import SESSION_TIMEOUT_MINUTES
    app.config['SESSION_TIMEOUT_MINUTES'] = int(
        os.environ.get('SESSION_TIMEOUT_MINUTES', SESSION_TIMEOUT_MINUTES)
    )


def _register_blueprints(app):
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
    app.register_blueprint(warehouse_v2_bp)
    app.register_blueprint(scanner_bp)
    app.register_blueprint(magazyn_dostawy_bp)
    app.register_blueprint(traceability_bp)
    app.register_blueprint(inwentaryzacja_bp)
    app.register_blueprint(inwentaryzacja_produkcji_bp)
    app.register_blueprint(osip_bp)
    app.register_blueprint(maluchy_bp, url_prefix='/maluchy')


def _is_werkzeug_reloader_parent():
    if 'PYTEST_CURRENT_TEST' in os.environ:
        return False
    import sys
    main_script = sys.argv[0] if sys.argv and sys.argv[0] else ''
    reloader_enabled = (
        _env_bool('FLASK_USE_RELOADER') or _env_bool('RELOADER_ENABLED')
    )
    debug_mode = (
        _env_bool('FLASK_DEBUG')
        or _env_bool('DEBUG')
        or str(os.environ.get('FLASK_ENV', '')).lower() == 'development'
    )
    return bool(
        debug_mode
        and (reloader_enabled or main_script.endswith('app.py') or 'app.py' in main_script)
        and os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    )


def _maybe_start_background_daemons(app, is_reloader_parent):
    if 'PYTEST_CURRENT_TEST' in os.environ:
        app.logger.debug('Skipping background daemons under pytest')
        return

    default_enabled = not _is_production()
    enabled = _env_bool('ENABLE_BACKGROUND_DAEMONS', default_enabled)
    if not enabled:
        app.logger.info('Background daemons disabled for this process')
        return
    if is_reloader_parent:
        app.logger.debug('Skipping background daemons in Werkzeug reloader parent')
        return
    start_daemon_threads(app, cleanup_enabled=True)


def create_app(config_secret_key=None, init_db=True):
    """Create and securely configure the Flask application."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    app = Flask(
        __name__,
        root_path=project_root,
        template_folder=os.path.join(project_root, 'templates'),
        static_folder=os.path.join(project_root, 'static'),
    )

    _restore_fallback_config(app, project_root)
    _configure_secret_key(app, config_secret_key)
    _configure_sessions(app)

    setup_logging(app)
    register_error_handlers(app)
    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.cache = None
    app.config['TEMPLATES_AUTO_RELOAD'] = not _is_production()

    register_legacy_secret_rejection(app)
    register_middleware(app)
    register_role_integrity_check(app)
    _register_blueprints(app)
    register_legacy_print_hardening(app)
    register_runtime_security_hardening(app)
    register_admin_security_hardening(app)

    if _debug_routes_enabled():
        register_debug_routes(app)

    app.jinja_env.filters['format_czasu'] = format_godziny
    register_contexts(app)

    is_reloader_parent = _is_werkzeug_reloader_parent()
    _maybe_start_background_daemons(app, is_reloader_parent)

    skip_db_setup = _env_bool('SKIP_DB_SETUP', False) or is_reloader_parent
    if init_db and not skip_db_setup:
        try:
            if 'PYTEST_CURRENT_TEST' not in os.environ:
                db.setup_database()
            else:
                app.logger.debug('Skipping setup_database() under pytest')
        except Exception as exc:
            app.logger.exception('setup_database() failed or skipped: %s', exc)

    apply_proxy_policy(app)

    try:
        from app.cli import register_cli_commands
        register_cli_commands(app)
    except Exception as exc:
        app.logger.warning('Failed to register CLI commands: %s', exc)

    return app


def register_debug_routes(app):
    """Register local-only diagnostics when explicitly enabled."""
    @app.route('/__debug/url_map')
    def debug_url_map():
        rules = [
            {
                'rule': str(rule.rule),
                'endpoint': rule.endpoint,
                'methods': sorted(list(rule.methods)),
            }
            for rule in app.url_map.iter_rules()
        ]
        return {'rules': rules}
