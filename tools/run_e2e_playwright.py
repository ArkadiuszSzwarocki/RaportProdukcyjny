import os
import subprocess
import time
from datetime import date
import requests
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `from tools.seed_e2e_plan import create_plan` works
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.seed_e2e_plan import create_plan


def run():
    base = os.environ.get('E2E_BASE_URL', 'http://localhost:8082')
    print('Seeding test plan...')
    pid = create_plan()
    print('Created plan id=', pid)

    # Run the Playwright UI script (tools/ui_test_playwright.py)
    env = os.environ.copy()
    env['PLAYWRIGHT_HEADLESS'] = env.get('PLAYWRIGHT_HEADLESS', '1')
    env['PLAYWRIGHT_SLOW_MO'] = env.get('PLAYWRIGHT_SLOW_MO', '0')

    print('Running Playwright script (tools/ui_test_playwright.py)')
    # wait for server readiness by polling /api/bufor
    import requests as _req
    ready = False
    for i in range(30):
        try:
            rr = _req.get(f"{base}/api/bufor", timeout=2)
            if rr.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)
    if not ready:
        print('Server not ready at', base, '- aborting Playwright run')
        # write a short log and return
        lp = os.path.join(str(ROOT), 'tools', 'e2e_playwright_runner.log')
        with open(lp, 'a', encoding='utf-8') as lf:
            lf.write('Server not ready at ' + base + '\n')
        return
    log_path = os.path.join(str(ROOT), 'tools', 'e2e_playwright_runner.log')
    with open(log_path, 'w', encoding='utf-8') as lf:
        try:
            p = subprocess.run([os.sys.executable, 'tools/ui_test_playwright.py'], env=env, capture_output=True, text=True, timeout=300)
            lf.write('=== STDOUT ===\n')
            lf.write(p.stdout or '')
            lf.write('\n=== STDERR ===\n')
            lf.write(p.stderr or '')
            lf.write(f"\nRETURN CODE: {p.returncode}\n")
            print('Playwright exited with code', p.returncode, '— logs written to', log_path)
        except subprocess.TimeoutExpired as te:
            lf.write('TIMEOUT: ' + repr(te) + '\n')
            print('Playwright timed out; see', log_path)
        except Exception as e:
            lf.write('EXCEPTION: ' + repr(e) + '\n')
            print('Playwright run failed; see', log_path)

    # Give server a moment to persist any DB changes
    time.sleep(1)

    # Check public bufor API for the created plan
    qdate = str(date.today())
    try:
        r = requests.get(f"{base}/api/bufor", params={'data': qdate}, timeout=10)
        if r.status_code == 200:
            j = r.json()
            buf = j.get('bufor', [])
            found = any(int(x.get('id') or 0) == int(pid or 0) for x in buf)
            print('Plan found in /api/bufor:', found)
            if not found:
                print('Bufor entries returned:', buf)
        else:
            print('Failed to query /api/bufor', r.status_code, r.text[:200])
    except Exception as e:
        print('Error querying bufor API:', e)


if __name__ == '__main__':
    run()
