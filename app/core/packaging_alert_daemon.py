"""Explicitly enabled stock minimum alerts daemon without browser polling."""
import logging
import os
import threading
import time
from cryptography.fernet import Fernet


def _stock_alerts_enabled() -> bool:
    """Allow alerts only on the designated report/mail host unless explicitly enabled."""
    raw = os.getenv('ENABLE_STOCK_ALERTS')
    if raw is not None and raw.strip():
        return raw.strip().lower() in ('true', '1', 'yes', 'on')
    return os.getenv('ENABLE_AUTO_REPORT_SCHEDULER', '').strip().lower() in ('true', '1', 'yes', 'on')


def _alert_loop(app):
    from app.services.packaging_stock_alerts import run_check
    while True:
        try:
            with app.app_context():
                run_check()
        except Exception:
            logging.getLogger(__name__).exception('Packaging stock alert check failed')
        time.sleep(300)


def start_packaging_alerts(app):
    """Start background minimum stock checks on explicitly opted-in mail hosts."""
    from app.core.instance_mode import is_test_instance
    if is_test_instance() or 'PYTEST_CURRENT_TEST' in os.environ or not _stock_alerts_enabled():
        return False
    if app.extensions.get('packaging_alerts_started'):
        return True
    try:
        Fernet((os.getenv('ENCRYPTION_KEY') or '').strip().encode('ascii'))
    except (ValueError, UnicodeEncodeError):
        logging.getLogger(__name__).error('STOCK_ALERTS_START_BLOCKED: missing or invalid ENCRYPTION_KEY')
        return False
    thread = threading.Thread(target=_alert_loop, args=(app,), name='packaging-stock-alerts', daemon=True)
    app.extensions['packaging_alerts_started'] = True
    try:
        thread.start()
    except Exception:
        app.extensions.pop('packaging_alerts_started', None)
        raise
    return True
