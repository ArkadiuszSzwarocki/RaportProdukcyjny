import os
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright


def run(headless=True, slow_mo=0):
    base = os.environ.get('E2E_BASE_URL', 'http://localhost:8082')
    target_date = os.environ.get('E2E_DATE', date.today().isoformat())
    out_dir = Path.cwd() / 'raporty'
    out_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # login
        page.goto(f"{base}/login")
        try:
            page.fill('input[name=login]', os.environ.get('E2E_LOGIN', 'admin'))
            page.fill('input[name=haslo]', os.environ.get('E2E_PASS', 'masterkey'))
            page.click('button[type=submit]')
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception as e:
            print('Login failed:', e)

        formats = [('excel', 'xlsx'), ('pdf', 'pdf'), ('email', 'txt')]
        for fmt, ext in formats:
            url = f"{base}/api/pobierz-raport?format={fmt}&data={target_date}"
            print('Requesting', url)
            try:
                with page.expect_download(timeout=10000) as download_info:
                    page.goto(url)
                download = download_info.value
                save_path = out_dir / f'Playwright_Raport_{target_date}.{ext}'
                download.save_as(str(save_path))
                print('Saved', save_path)
            except Exception as e:
                # fallback: try fetch via JavaScript (for text responses)
                try:
                    resp = page.evaluate(f"(async ()=>{{ const r=await fetch('{url}', {{credentials:'include'}}); const b=await r.arrayBuffer(); return Array.from(new Uint8Array(b)); }})();")
                    if resp and isinstance(resp, list):
                        data = bytes(resp)
                        save_path = out_dir / f'Playwright_Raport_{target_date}.{ext}'
                        with open(save_path, 'wb') as fh:
                            fh.write(data)
                        print('Saved fallback', save_path)
                    else:
                        print('Failed to fetch', url, 'fallback returned', type(resp))
                except Exception as e2:
                    print('Download failed for', fmt, e, e2)

        context.close()
        browser.close()


if __name__ == '__main__':
    headless_env = os.environ.get('PLAYWRIGHT_HEADLESS', '0')
    headless = not (headless_env in ('0', 'false', 'False'))
    slow_mo = int(os.environ.get('PLAYWRIGHT_SLOW_MO', '200'))
    run(headless=headless, slow_mo=slow_mo)
