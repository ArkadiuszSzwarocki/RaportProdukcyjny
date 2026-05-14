import subprocess
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCRIPT = BASE / 'ui_test_playwright.py'

def safe_move(src, dest):
    try:
        if dest.exists():
            dest.unlink()
        shutil.move(str(src), str(dest))
    except Exception:
        try:
            # fallback copy
            shutil.copy2(str(src), str(dest))
        except Exception:
            pass

def run_repeat(n=5, delay=1):
    n = int(n)
    for i in range(1, n+1):
        print(f'Run {i}/{n}...')
        proc = subprocess.run([sys.executable, str(SCRIPT)])
        # move artifacts to numbered files
        idx = str(i).zfill(2)
        safe_move(BASE / 'playwright_snapshot.png', BASE / f'playwright_snapshot_{idx}.png')
        safe_move(BASE / 'last_zasyp_response.html', BASE / f'last_zasyp_response_{idx}.html')
        safe_move(BASE / 'playwright_network.log', BASE / f'playwright_network_{idx}.log')
        safe_move(BASE / 'playwright_console.log', BASE / f'playwright_console_{idx}.log')
        safe_move(BASE / 'playwright_trace.zip', BASE / f'playwright_trace_{idx}.zip')
        # small delay between runs
        time.sleep(delay)

if __name__ == '__main__':
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    run_repeat(iters, delay)
