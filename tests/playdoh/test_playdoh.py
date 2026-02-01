import os
import subprocess
import time
import pytest

LOGS_FILE = 'tools/playwright_console.log'


pytestmark = pytest.mark.skipif(os.environ.get('RUN_PLAYDOH') != '1', reason='Playdoh tests disabled by default; set RUN_PLAYDOH=1 to run')


def test_run_playdoh_script(tmp_path):
    env = os.environ.copy()
    env['PLAYWRIGHT_HEADLESS'] = '1'
    env['PLAYWRIGHT_SLOW_MO'] = '0'

    # run the existing UI test script; it should write logs to tools/playwright_console.log
    proc = subprocess.run([env.get('PYTHON', 'python'), 'tools/ui_test_playwright.py'], env=env, timeout=120)
    assert proc.returncode == 0

    # wait briefly for logs to be flushed
    time.sleep(0.5)
    assert os.path.exists(LOGS_FILE), f"Expected logs at {LOGS_FILE}"
    with open(LOGS_FILE, 'r', encoding='utf-8') as fh:
        data = fh.read()
    assert 'Saved page screenshot' in data or 'Saved Playwright trace' in data or len(data) > 0
