from playwright.sync_api import sync_playwright
import time

URL = 'http://localhost:8082/?sekcja=Zasyp'

logs = []
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    def on_console(msg):
        try:
            text = msg.text()
        except Exception:
            text = str(msg)
        logs.append((msg.type, text))

    def on_page_error(exc):
        errors.append(str(exc))

    page.on('console', on_console)
    page.on('pageerror', on_page_error)

    print('Navigating to', URL)
    page.goto(URL, wait_until='networkidle', timeout=15000)
    time.sleep(0.5)

    # Interact: click hamburger if present to open/close sidebar
    try:
        if page.query_selector('#hamburgerBtn'):
            print('Clicking hamburger to open sidebar')
            page.click('#hamburgerBtn')
            time.sleep(0.3)
            page.click('#hamburgerBtn')
            time.sleep(0.3)
    except Exception as e:
        print('Hamburger click failed:', e)

    # Trigger another navigation and interactions
    page.goto(URL.replace('Zasyp', 'Workowanie'), wait_until='networkidle')
    time.sleep(0.3)
    page.goto(URL, wait_until='networkidle')
    time.sleep(0.3)

    # Wait a moment for console messages
    time.sleep(1.0)

    print('\nConsole messages captured:')
    for t, msg in logs:
        print(f'[{t}] {msg}')

    if errors:
        print('\nPage errors:')
        for e in errors:
            print(e)

    browser.close()
