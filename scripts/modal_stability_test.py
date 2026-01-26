from playwright.sync_api import sync_playwright
import time

URL_WORK = 'http://localhost:8082/?sekcja=Workowanie'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(ignore_https_errors=True, viewport={'width':1280,'height':800})
    page = context.new_page()

    # try Zasyp first, then Workowanie
    page.goto('http://localhost:8082/?sekcja=Zasyp', wait_until='networkidle')
    time.sleep(0.3)
    # find any element that opens a modal via openModal('id')
    opener = None
    for el in page.query_selector_all('[onclick]'):
        on = page.evaluate('(el) => el.getAttribute("onclick")', el)
        if on and 'openModal' in on:
            opener = el
            break

    if not opener:
        print('No modal opener found on page')
        browser.close()
        exit(1)

    # click opener
    opener.click()
    time.sleep(0.3)

    # find visible modal
    modal = None
    for m in page.query_selector_all('.modal-popup'):
        vis = page.evaluate('(el) => getComputedStyle(el).visibility', m)
        if vis == 'visible':
            modal = m
            break

    if not modal:
        print('No visible modal found after click')
        browser.close()
        exit(1)

    rect1 = page.evaluate('(el) => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; }', modal)
    print('Modal rect before hover:', rect1)

    # try to hover at a point just below modal (should be overlay intercepting)
    target_x = rect1['x'] + rect1['w']/2
    target_y = rect1['y'] + rect1['h'] + 10
    try:
        page.mouse.move(target_x, target_y)
        time.sleep(0.3)
    except Exception as e:
        print('Mouse move failed:', e)

    rect2 = page.evaluate('(el) => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; }', modal)
    print('Modal rect after hover:', rect2)

    moved = abs(rect1['x']-rect2['x'])>1 or abs(rect1['y']-rect2['y'])>1
    print('Modal moved?', moved)

    browser.close()
