from playwright.sync_api import sync_playwright
import time

URL_ZASYP = 'http://localhost:8082/?sekcja=Zasyp'
URL_WORK = 'http://localhost:8082/?sekcja=Workowanie'

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

    def snapshot(title):
        print('\n---', title, '---')

    try:
        print('Go to Zasyp')
        page.goto(URL_ZASYP, wait_until='networkidle', timeout=15000)
        time.sleep(0.5)

        # open sidebar briefly
        try:
            if page.query_selector('#hamburgerBtn'):
                page.click('#hamburgerBtn')
                time.sleep(0.2)
                page.click('#hamburgerBtn')
                time.sleep(0.2)
        except Exception:
            pass

        # Try to click first + SZARŻA button (by text)
        try:
            btn = page.locator("text=+ SZARŻA").nth(0)
            if btn.count() and btn.is_visible():
                print('Click + SZARŻA')
                btn.click()
                time.sleep(0.3)
                # capture modal rect if any visible
                try:
                    mod = None
                    for m in page.query_selector_all('.modal-popup'):
                        vis = page.evaluate('(el) => getComputedStyle(el).visibility', m)
                        if vis == 'visible':
                            mod = m
                            break
                    if mod:
                        rect1 = page.evaluate('(el)=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}', mod)
                        print('Modal rect before hover:', rect1)
                        # hover below modal
                        tx = rect1['x'] + rect1['w']/2
                        ty = rect1['y'] + rect1['h'] + 10
                        page.mouse.move(tx, ty)
                        time.sleep(0.3)
                        rect2 = page.evaluate('(el)=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}', mod)
                        print('Modal rect after hover:', rect2)
                        moved = abs(rect1['x']-rect2['x'])>1 or abs(rect1['y']-rect2['y'])>1
                        print('Modal moved?', moved)
                except Exception:
                    pass
        except Exception:
            pass

        # Try STOP button
        try:
            stopBtn = page.locator("text=STOP").first()
            if stopBtn.count() and stopBtn.is_visible():
                print('Click STOP')
                stopBtn.click()
                time.sleep(0.3)
                # click ANULUJ inside modal
                try:
                    an = page.locator('text=ANULUJ').first()
                    if an.count():
                        an.click()
                        time.sleep(0.2)
                except Exception:
                    pass
        except Exception:
            pass

        # Navigate to Workowanie
        print('Go to Workowanie')
        page.goto(URL_WORK, wait_until='networkidle')
        time.sleep(0.5)

        # Click + PALETA / + BIGBAG
        try:
            pal = page.locator("text=+ PALETA").first()
            if not pal.count() or not pal.is_visible():
                pal = page.locator("text=+ BIGBAG").first()
            if pal.count() and pal.is_visible():
                print('Click + PALETA/BIGBAG')
                pal.click()
                time.sleep(0.3)
                # click ANULUJ
                try:
                    an = page.locator('text=ANULUJ').first()
                    if an.count():
                        an.click()
                        time.sleep(0.2)
                except Exception:
                    pass
        except Exception:
            pass

        # Click any DODAJ (submit) button visible (non-destructive: won't fill forms)
        try:
            dod = page.locator('text=DODAJ').first()
            if dod.count() and dod.is_visible():
                print('Click DODAJ (if safe)')
                # avoid submitting forms that require values; try clicking but catch navigation
                try:
                    dod.click()
                    time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass

    except Exception as e:
        print('Navigation/test exception:', e)

    # Wait for console
    time.sleep(1.0)

    print('\nConsole messages captured:')
    for t, msg in logs:
        print(f'[{t}] {msg}')

    if errors:
        print('\nPage errors:')
        for e in errors:
            print(e)

    browser.close()
