from playwright.sync_api import sync_playwright
import time

URL = 'http://localhost:8082/?sekcja=Zasyp'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    page.goto(URL, wait_until='networkidle', timeout=15000)
    time.sleep(0.5)

    # Click + SZARŻA
    try:
        btn = page.locator("text=+ SZARŻA").nth(0)
        if btn.count() and btn.is_visible():
            print('Clicked + SZARŻA')
            btn.click()
            time.sleep(0.4)
    except Exception as e:
        print('Click error', e)

    # Count modal-popup total and visible
    total_modals = page.evaluate('() => document.querySelectorAll(\'.modal-popup\').length')
    visible_modals = page.evaluate("() => Array.from(document.querySelectorAll('.modal-popup')).filter(m=>getComputedStyle(m).visibility==='visible' || getComputedStyle(m).opacity==='1').length")
    open_drawers = page.evaluate("() => document.querySelectorAll('.side-drawer.side-drawer--open').length")
    overlay_attr = page.evaluate("() => (function(){var o=document.getElementById('modalOverlay'); if(!o) return null; return {data_forced: o.getAttribute('data-forced-hidden'), style_display: o.style.display, style_visibility: o.style.visibility, computed_visibility:getComputedStyle(o).visibility, computed_opacity:getComputedStyle(o).opacity};})()")

    print('total_modals', total_modals)
    print('visible_modals', visible_modals)
    print('open_drawers', open_drawers)
    print('overlay', overlay_attr)

    # dump first visible modal ids
    ids = page.evaluate("() => Array.from(document.querySelectorAll('.modal-popup')).filter(m=>getComputedStyle(m).visibility==='visible' || getComputedStyle(m).opacity==='1').map(m=>m.id)")
    print('visible_modal_ids', ids)

    browser.close()
