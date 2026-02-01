from playwright.sync_api import sync_playwright
import os

TRACE_PATH = os.path.join('tools','interactive_trace.zip')
SHOT_PATH = os.path.join('tools','interactive_screenshot.png')
HAR_PATH = os.path.join('tools','interactive_network.har')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=50)
    context = browser.new_context(record_har_path=HAR_PATH)
    page = context.new_page()
    # start tracing
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    print('Navigating to /?sekcja=Zasyp — proszę zalogować się i sprawdzić DevTools. Naciśnij Enter, gdy skończysz...')
    page.goto('http://localhost:8082/?sekcja=Zasyp')
    input()
    # save artifacts
    context.tracing.stop(path=TRACE_PATH)
    page.screenshot(path=SHOT_PATH, full_page=True)
    context.close()
    browser.close()
    print('Zapisano:', TRACE_PATH, SHOT_PATH, HAR_PATH)
