import os
import time
from playwright.sync_api import sync_playwright

LOG = 'tools/show_workowanie.log'
OUT = 'tools/workowanie_paleta.png'

def run():
    base = os.environ.get('APP_BASE', 'http://localhost:8082')
    logs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.on('console', lambda msg: logs.append(f'CONSOLE {msg.type}: {msg.text}'))
        try:
            page.goto(f'{base}/login')
            page.fill('input[name=login]', 'admin')
            page.fill('input[name=haslo]', 'masterkey')
            page.click('button[type=submit]')
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception as e:
            logs.append('Login failed: ' + str(e))

        try:
            page.goto(f'{base}/?sekcja=Workowanie')
            page.wait_for_load_state('networkidle', timeout=8000)
        except Exception as e:
            logs.append('Goto workowanie failed: ' + str(e))

        # try to detect paleta by common indicators
        found = False
        try:
            if page.locator('text=paleta').count() > 0:
                found = True
        except Exception:
            pass
        try:
            # check for weight or id text
            if page.locator('text=1000').count() > 0 or page.locator('text=499').count() > 0:
                found = True
        except Exception:
            pass

        try:
            page.screenshot(path=OUT, full_page=True)
            logs.append('Saved screenshot ' + OUT)
        except Exception as e:
            logs.append('Screenshot failed: ' + str(e))

        logs.append('Paleta visible: ' + str(found))
        try:
            ctx.close()
            browser.close()
        except Exception:
            pass

    with open(LOG, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(logs))
    print('Wrote', LOG)

if __name__ == '__main__':
    run()
