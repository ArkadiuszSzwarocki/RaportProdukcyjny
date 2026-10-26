# cspell:words dotenv
"""Run the local application against the existing QNAP test database."""
import argparse
import os
from pathlib import Path
import secrets
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def configure_environment():
    from dotenv import dotenv_values, load_dotenv
    profile = PROJECT / '.env.local-test'
    if not profile.exists():
        profile.write_text((PROJECT / 'local-test.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    if not dotenv_values(profile).get('SECRET_KEY'):
        with profile.open('a', encoding='utf-8') as output:
            output.write('\nSECRET_KEY=' + secrets.token_hex(32) + '\n')
    load_dotenv(profile, override=True)
    load_dotenv(PROJECT / '.env', override=False)
    # Configure only this local process; keep the QNAP application independent.
    os.environ.update(APP_INSTANCE_MODE='local', DB_NAME='biblioteka_testowa', DB_NAME_LOCKED='false',
        FLASK_ENV='development', ENV='development', LOCAL_ENV='true', IS_LOCAL='true',
        FLASK_DEBUG='0', DEBUG='false', ENABLE_DEBUG_ROUTES='false',
        HOST='127.0.0.1', PORT='8082', APP_BASE_URL='http://127.0.0.1:8082',
        TRUSTED_HOSTS='127.0.0.1,localhost', SESSION_COOKIE_SECURE='false',
        ALLOW_RUNTIME_DB_SWITCH='true', DB_ALLOW_LOCALHOST_FALLBACK='false',
        ENABLE_BACKGROUND_DAEMONS='true', ENABLE_MQTT_BRIDGE='true',
        ENABLE_AUTO_REPORT_SCHEDULER='true', PRINTER_BRIDGE_AUTOSTART='true',
        PRINTER_ALLOW_DIRECT_TCP_FALLBACK='true', SKIP_DB_SETUP='true')


def verify_database():
    import mysql.connector
    from app.config import DB_CONFIG
    from app.core.database import get_active_database_name
    selected_database = get_active_database_name()
    config = dict(DB_CONFIG, use_pure=True)
    connection = mysql.connector.connect(**config)
    try:
        cursor = connection.cursor()
        cursor.execute('START TRANSACTION READ ONLY')
        cursor.execute('SELECT DATABASE()')
        if cursor.fetchone()[0] != selected_database:
            raise RuntimeError('The server selected an unexpected database')
        cursor.close()
    finally:
        connection.rollback()
        connection.close()
    print(f'Verified SQL connection: {selected_database} (read-only probe)', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Verify the configured SQL connection without starting the app')
    args = parser.parse_args()
    os.chdir(PROJECT)
    configure_environment()
    verify_database()
    if args.check_only:
        return
    if os.getenv('LOCAL_STARTUP_TRACE') == 'true':
        import faulthandler
        faulthandler.dump_traceback_later(15, repeat=False)
    from app.core.factory import create_app
    from waitress import serve
    application = create_app(init_db=False)
    if os.getenv('LOCAL_STARTUP_TRACE') == 'true':
        faulthandler.cancel_dump_traceback_later()
    print('LOCAL APPLICATION: http://127.0.0.1:8082', flush=True)
    print('Email, printing, MQTT commands and background workers are enabled.', flush=True)
    serve(application, host='127.0.0.1', port=8082, threads=8)


if __name__ == '__main__':
    main()
