from playwright.sync_api import sync_playwright
import os
import time

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:8082')
LOGIN = os.environ.get('ATK_LOGIN')
PASSWORD = os.environ.get('ATK_PASSWORD')

import sys
if len(sys.argv) >= 3:
    LOGIN = sys.argv[1]
    PASSWORD = sys.argv[2]

console_lines = []
network_lines = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.on('console', lambda msg: console_lines.append(f"{msg.type}: {msg.text}"))
        page.on('pageerror', lambda exc: console_lines.append(f"pageerror: {exc}"))

        def on_request(req):
            network_lines.append(f"REQ {req.method} {req.url}")
        def on_response(resp):
            network_lines.append(f"RESP {resp.status} {resp.url}")

        page.on('request', on_request)
        page.on('response', on_response)

        # Open base
        page.goto(BASE, wait_until='networkidle')

        # If login provided, attempt login
        if LOGIN and PASSWORD:
            try:
                # fill standard fields if present
                if page.query_selector('input[name=login]'):
                    page.fill('input[name=login]', LOGIN)
                elif page.query_selector('#login'):
                    page.fill('#login', LOGIN)
                if page.query_selector('input[name=haslo]'):
                    page.fill('input[name=haslo]', PASSWORD)
                elif page.query_selector('#haslo'):
                    page.fill('#haslo', PASSWORD)
                # submit first form by clicking the submit button (more like a real user)
                if page.query_selector('button[type=submit]'):
                    page.click('button[type=submit]')
                elif page.query_selector('form'):
                    # fallback to form submit
                    page.query_selector('form').evaluate('f => f.submit()')
                # wait for navigation / scripts to run
                try:
                    page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass
            except Exception as e:
                console_lines.append(f'login-exception: {e}')

        # Navigate directly to podsumowanie_szarz
        try:
            page.goto(f"{BASE}/podsumowanie_szarz", wait_until='networkidle')
        except Exception as e:
            console_lines.append(f'navigate-exception: {e}')

        # wait a bit for scripts to run
        time.sleep(1.5)

        # save artifacts
        with open('tmp_playwright_console.log', 'w', encoding='utf-8') as f:
            f.write('\n'.join(console_lines))
        with open('tmp_playwright_network.log', 'w', encoding='utf-8') as f:
            f.write('\n'.join(network_lines))
        page.screenshot(path='tmp_playwright.png', full_page=True)
        with open('tmp_playwright.html', 'w', encoding='utf-8') as f:
            f.write(page.content())

        browser.close()

if __name__ == '__main__':
    main()
