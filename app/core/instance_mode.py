"""Isolation and database selection for local application processes."""
import os


def is_local_instance():
    return os.getenv('APP_INSTANCE_MODE', '').strip().lower() == 'local'


def is_test_instance():
    return os.getenv('APP_INSTANCE_MODE', '').strip().lower() == 'test'


def database_name_locked():
    return os.getenv('APP_INSTANCE_MODE', '').strip().lower() == 'test' or os.getenv('DB_NAME_LOCKED', '').lower() in ('1', 'true', 'yes', 'on')


def configure_instance(app):
    if is_test_instance() or is_local_instance():
        from app.config import DB_CONFIG
        if not is_local_instance() and DB_CONFIG.get('database') != 'biblioteka_testowa':
            raise RuntimeError('The test instance requires DB_NAME=biblioteka_testowa')
        app.config['SESSION_COOKIE_NAME'] = 'raport_test_session'

    def instance_context():
        from app.core.database import get_active_database_name
        return {'test_instance': is_test_instance(), 'local_instance': is_local_instance(),
                'active_database': get_active_database_name()}
    app.context_processor(instance_context)
