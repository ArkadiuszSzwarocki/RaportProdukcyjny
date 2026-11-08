"""Background checks without browser polling or page reloads."""
import logging
import threading
import time


def start_packaging_alerts(app):
    from app.core.instance_mode import is_test_instance
    if is_test_instance() or app.extensions.get('packaging_alerts_started'):
        return
    app.extensions['packaging_alerts_started'] = True

    def loop():
        from app.services.packaging_stock_alerts import run_check
        while True:
            try:
                with app.app_context():
                    run_check()
            except Exception:
                logging.getLogger(__name__).exception('Packaging stock alert check failed')
            time.sleep(300)

    threading.Thread(target=loop, name='packaging-stock-alerts', daemon=True).start()
