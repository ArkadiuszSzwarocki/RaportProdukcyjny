import os
from playwright.sync_api import sync_playwright

OUT = 'tools/paleta_499.png'
LOG = 'tools/crop_paleta.log'

def run():
    base = os.environ.get('APP_BASE', 'http://localhost:8082')
    logs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
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

        found = False
        # try several locators for paleta (id or weight)
        candidates = ["text=499", "text=1000", "text=Paleta", "text=paleta"]
        el = None
        for sel in candidates:
            try:
                loc = page.locator(sel).first
                loc.wait_for(timeout=2000)
                el = loc.element_handle()
                if el:
                    found = True
                    logs.append('Found element with selector: ' + sel)
                    break
            except Exception:
                continue

        if not el:
            # as a fallback, try to screenshot a reasonable region in the middle
            try:
                page.screenshot(path=OUT, full_page=False)
                logs.append('Fallback full-page crop saved to ' + OUT)
            except Exception as e:
                logs.append('Fallback screenshot failed: ' + str(e))
        else:
            try:
                el.screenshot(path=OUT)
                logs.append('Saved element screenshot to ' + OUT)
            except Exception as e:
                logs.append('Element screenshot failed: ' + str(e))

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
