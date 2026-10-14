"""Run application background daemons in one dedicated process."""

import os
import signal
import time


os.environ['ENABLE_BACKGROUND_DAEMONS'] = 'true'
os.environ.setdefault('SKIP_DB_SETUP', 'true')

from app.core.factory import create_app  # noqa: E402


_running = True


def _stop(_signum, _frame):
    global _running
    _running = False


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    app = create_app(init_db=False)
    app.logger.info('Dedicated background daemon process started')
    while _running:
        time.sleep(1)
    app.logger.info('Dedicated background daemon process stopping')


if __name__ == '__main__':
    main()
