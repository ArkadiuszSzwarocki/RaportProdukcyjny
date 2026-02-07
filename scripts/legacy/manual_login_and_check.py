from playwright.sync_api import sync_playwright
import time

URL = 'http://localhost:8082/?sekcja=Zasyp'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    print('Opened browser. Please log in manually in the opened window if required.')
    print('When ready, press Enter here to continue the automated checks...')
    page.goto(URL)
    input()  # wait for user to press Enter in terminal after logging in

    # Go to page after login to ensure session is used
    page.goto(URL, wait_until='networkidle')
    time.sleep(0.5)

    # Try to open a modal by clicking any opener
    opener = None
    for el in page.query_selector_all('[onclick]'):
        on = page.evaluate('(el) => el.getAttribute("onclick")', el)
        if on and 'openModal' in on:
            opener = el
            break

    if opener:
        try:
            opener.click()
            time.sleep(0.3)
        except Exception as e:
            print('Click failed:', e)
    else:
        print('No modal opener found. Ensure the page has action buttons visible.')

    # Find visible modal
    mod = None
    for m in page.query_selector_all('.modal-popup'):
        try:
            vis = page.evaluate('(el) => getComputedStyle(el).visibility', m)
            op = float(page.evaluate('(el) => getComputedStyle(el).opacity', m) or 0)
            if vis == 'visible' and op > 0:
                mod = m
                break
        except Exception:
            continue

    if not mod:
        print('No visible modal detected.')
    else:
        rect1 = page.evaluate('(el)=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}', mod)
        print('Modal rect before hover:', rect1)
        tx = rect1['x'] + rect1['w']/2
        ty = rect1['y'] + rect1['h'] + 10
        try:
            page.mouse.move(tx, ty)
            time.sleep(0.4)
        except Exception as e:
            print('Mouse move failed:', e)
        rect2 = page.evaluate('(el)=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}', mod)
        print('Modal rect after hover:', rect2)
        moved = abs(rect1['x']-rect2['x'])>1 or abs(rect1['y']-rect2['y'])>1
        print('Modal moved?', moved)

    print('Test finished. Close the browser when done.')
    input('Press Enter to close browser and exit...')
    browser.close()
