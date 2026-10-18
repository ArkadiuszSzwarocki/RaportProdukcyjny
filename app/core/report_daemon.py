"""Explicitly enabled report scheduler, independent from production hardware jobs."""
import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _report_lock_names(connection):
    return ('auto_report_daemon_leader', 'auto_report_daemon_leader_' + connection.database)


def _release_report_lease(connection):
    try:
        cursor = connection.cursor()
        try:
            for name in _report_lock_names(connection):
                cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))
                cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()


def _acquire_report_lease():
    from app.db import get_db_connection
    connection = get_db_connection()
    cursor = connection.cursor()
    acquired = False
    try:
        for name in _report_lock_names(connection):
            cursor.execute('SELECT GET_LOCK(%s,0)', (name,))
            result = cursor.fetchone()
            if not result or result[0] != 1:
                return None
        acquired = True
        return connection
    finally:
        cursor.close()
        if not acquired:
            try:
                _release_report_lease(connection)
            except Exception:
                logger.warning('Could not release failed report lease')


def start_report_scheduler(app):
    # Local/test copies must not reserve production report attempts implicitly.
    if str(os.getenv('ENABLE_AUTO_REPORT_SCHEDULER', '')).lower() not in ('true','1','yes','on'):
        return False
    if app.extensions.get('daily_report_scheduler_started'):
        return True
    try:
        Fernet((os.getenv('ENCRYPTION_KEY') or '').strip().encode('ascii'))
    except (ValueError, UnicodeEncodeError):
        logger.error('AUTO_REPORT_START_BLOCKED: missing or invalid ENCRYPTION_KEY; no report lock acquired')
        return False
    thread = threading.Thread(target=_report_loop, args=(app,), daemon=True, name='daily-report-scheduler')
    app.extensions['daily_report_scheduler_started'] = True
    try:
        thread.start()
    except Exception:
        app.extensions.pop('daily_report_scheduler_started', None)
        raise
    return True


def _report_loop(app):
    from app.services.daily_report_scheduler import run_daily_reports
    leader = None
    while True:
        try:
            if leader is None:
                leader = _acquire_report_lease()
            if leader is None:
                time.sleep(5)
                continue
            try:
                leader.ping(reconnect=False, attempts=1, delay=0)
            except Exception:
                _release_report_lease(leader)
                leader = None
                time.sleep(2)
                continue
            with app.app_context():
                run_daily_reports(datetime.now(ZoneInfo('Europe/Warsaw')))
        except Exception:
            logger.exception('Daily report scheduler tick failed')
        time.sleep(10)
