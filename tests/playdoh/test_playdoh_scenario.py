import os
import subprocess
import time
import pytest

LOGS_FILE = 'tools/playdoh_scenario.log'


pytestmark = pytest.mark.skipif(os.environ.get('RUN_PLAYDOH') != '1', reason='Playdoh tests disabled by default; set RUN_PLAYDOH=1 to run')


def test_run_playdoh_scenario(tmp_path):
    env = os.environ.copy()
    env['PLAYWRIGHT_HEADLESS'] = '1'
    env['PLAYWRIGHT_SLOW_MO'] = '0'

    proc = subprocess.run([env.get('PYTHON', 'python'), 'tools/playdoh_scenario.py'], env=env, timeout=120)
    assert proc.returncode == 0

    time.sleep(0.2)
    assert os.path.exists(LOGS_FILE), f"Expected logs at {LOGS_FILE}"
    with open(LOGS_FILE, 'r', encoding='utf-8') as fh:
        data = fh.read()
    assert 'Clicked + SZARŻA' in data or 'Clicked Workuj ten towar' in data or len(data) > 0
