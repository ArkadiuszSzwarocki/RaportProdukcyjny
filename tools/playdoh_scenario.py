import os
import time
import requests
from playwright.sync_api import sync_playwright

LOGS_FILE = 'tools/playdoh_scenario.log'


def run():
    headless_env = os.environ.get('PLAYWRIGHT_HEADLESS', '1')
    headless = False if headless_env in ('0', 'false', 'False') else True
    slow_mo = int(os.environ.get('PLAYWRIGHT_SLOW_MO', '0'))

    logs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        ctx = browser.new_context()
        page = ctx.new_page()

        page.on('console', lambda msg: logs.append(f"CONSOLE {msg.type}: {msg.text}"))
        page.on('pageerror', lambda exc: logs.append(f"PAGEERROR: {exc}"))

        def on_request(r):
            logs.append(f"REQUEST {r.method} {r.url}")
        def on_response(r):
            logs.append(f"RESPONSE {r.status} {r.url}")
        page.on('request', on_request)
        page.on('response', on_response)

        # Intercept telemetry openmodal calls (some UI code posts here) and return 200
        def _telemetry_handler(route, request):
            try:
                route.fulfill(status=200, body='{}', headers={'Content-Type': 'application/json'})
            except Exception:
                route.continue_()

        page.route('**/telemetry/openmodal', _telemetry_handler)

        # Proxy legacy root endpoints to /api/* to avoid server 404/500 from form submissions
        def _proxy_root_to_api(route, request):
            try:
                url = request.url
                method = request.method
                post_data = request.post_data or ''
                # map /start_zlecenie/<id> -> /api/start_zlecenie/<id>
                # avoid double "/api/api/..." when URL already contains "/api/"
                if '/api/start_zlecenie/' in url:
                    target = url
                elif '/start_zlecenie/' in url:
                    target = url.replace('/start_zlecenie/', '/api/start_zlecenie/')
                elif '/api/dodaj_palete/' in url:
                    target = url
                elif '/dodaj_palete/' in url:
                    target = url.replace('/dodaj_palete/', '/api/dodaj_palete/')
                else:
                    route.continue_()
                    return

                # forward request to server using requests, preserve original headers (cookies etc.)
                headers = dict(request.headers)
                # ensure AJAX header so API returns JSON instead of redirect when appropriate
                headers.setdefault('X-Requested-With', 'XMLHttpRequest')
                # requests will set Host header itself
                headers.pop('host', None)
                data = post_data
                if isinstance(data, str):
                    data = data.encode('utf-8')
                r = requests.request(method, target, data=data, headers=headers, timeout=10, allow_redirects=False)
                resp_headers = {}
                if r.headers.get('Content-Type'):
                    resp_headers['Content-Type'] = r.headers.get('Content-Type')
                route.fulfill(status=r.status_code, body=r.content, headers=resp_headers)
            except Exception:
                try:
                    route.continue_()
                except Exception:
                    route.abort()

        page.route('**/start_zlecenie/*', _proxy_root_to_api)
        page.route('**/dodaj_palete/*', _proxy_root_to_api)

        base = os.environ.get('APP_BASE', 'http://localhost:8082')

        # login
        page.goto(f'{base}/login')
        try:
            page.fill('input[name=login]', 'admin')
            page.fill('input[name=haslo]', 'masterkey')
            page.click('button[type=submit]')
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception as e:
            logs.append('Login failed: ' + str(e))

        # 1) Zasyp -> click + SZARŻA
        try:
            page.goto(f'{base}/?sekcja=Zasyp', timeout=10000)
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            pass

        try:
            szarza = page.locator("text=+ SZARŻA").first
            szarza.wait_for(timeout=5000)
            szarza.click()
            logs.append('Clicked + SZARŻA')
        except Exception as e:
            logs.append('Failed to click + SZARŻA: ' + str(e))

        time.sleep(0.5)

        # 2) Bufor -> click "Workuj ten towar" (with robust fallbacks)
        plan_id = None
        try:
            # try to obtain plan id from requests/responses we've captured
            for L in reversed(logs):
                try:
                    if 'REQUEST' in L and '/api/szarza_page/' in L:
                        # extract digits at end
                        import re
                        m = re.search(r'/api/szarza_page/(\d+)', L)
                        if m:
                            plan_id = m.group(1)
                            break
                except Exception:
                    continue
        except Exception:
            pass

        try:
            page.goto(f'{base}/bufor', timeout=10000)
            page.wait_for_load_state('networkidle', timeout=8000)
            # prefer explicit onclick selector shim used by template
            work_btn = None
            try:
                work_btn = page.locator("button[onclick^=\"otworzOknoDodawaniaPalety\"]").first
                work_btn.wait_for(timeout=3000)
            except Exception:
                try:
                    work_btn = page.locator("text=Workuj ten towar").first
                    work_btn.wait_for(timeout=3000)
                except Exception:
                    work_btn = None

            if work_btn:
                work_btn.click()
                logs.append('Clicked Workuj ten towar (UI)')
            else:
                logs.append('Workuj button not found in UI')
                # fallback: if we have plan_id, call the API to move item to workowanie/start it
                if plan_id:
                    try:
                        # call full URL to avoid page-relative routing
                        start_js = "() => fetch('" + base + f"/api/start_zlecenie/{plan_id}' + '', {{method:'POST', credentials:'same-origin'}}).then(async r=>{{let t=await r.text(); return {{status:r.status, text:t}}}}).catch(e=>{{return {{status:'ERR', text:e.toString()}}}})"
                        start_res = page.evaluate(start_js)
                        logs.append('Direct API start_zlecenie response: ' + str(start_res))
                    except Exception as e:
                        logs.append('Direct API start_zlecenie failed: ' + str(e))
        except Exception as e:
            logs.append('Bufor interaction failed: ' + str(e))

        time.sleep(0.5)

        # 3) Workowanie -> find START and submit (or fallback to POST)
        try:
            page.goto(f'{base}/?sekcja=Workowanie', timeout=10000)
            page.wait_for_load_state('networkidle', timeout=8000)
            start_btn = None
            try:
                start_btn = page.locator("text=▶ START").first
                start_btn.wait_for(timeout=3000)
            except Exception:
                try:
                    start_btn = page.locator('.btn-start').first
                    start_btn.wait_for(timeout=3000)
                except Exception:
                    start_btn = None

            if start_btn:
                start_btn.click()
                logs.append('Clicked START (UI)')
            else:
                logs.append('Start button not found in UI')
                if not plan_id:
                    # try to extract plan_id again from logs
                    for L in reversed(logs):
                        if '/api/szarza_page/' in L:
                            import re
                            m = re.search(r'/api/szarza_page/(\d+)', L)
                            if m:
                                plan_id = m.group(1)
                                break
                if plan_id:
                    try:
                        js = "() => fetch('" + base + f"/api/start_zlecenie/{plan_id}', {{method:'POST', credentials:'same-origin'}}).then(async r=>{{let t=await r.text(); return {{status:r.status, text:t}}}}).catch(e=>({{status:'ERR', text:e.toString()}}))"
                        res = page.evaluate(js)
                        logs.append(f'Fallback start_zlecenie for {plan_id}: ' + str(res))
                    except Exception as e:
                        logs.append('Fallback start_zlecenie failed: ' + str(e))
        except Exception as e:
            logs.append('Start action failed: ' + str(e))

        time.sleep(0.5)

        # 4) Add pallet: find form input[name=waga_palety] and submit
        try:
            # ensure on workowanie page
            page.goto(f'{base}/?sekcja=Workowanie', timeout=10000)
            page.wait_for_load_state('networkidle', timeout=8000)
            inp = None
            try:
                inp = page.locator('input[name=waga_palety]').first
                inp.wait_for(timeout=3000)
            except Exception:
                inp = None

            if inp:
                inp.fill('1000')
                # click button '+ DODAJ PALETĘ' or similar
                add_btn = None
                try:
                    add_btn = page.locator("text=+ DODAJ PALETĘ").first
                    add_btn.wait_for(timeout=2000)
                except Exception:
                    add_btn = None

                if add_btn:
                    add_btn.click()
                    logs.append('Clicked + DODAJ PALETĘ (UI)')
                else:
                    # prefer API call over form.submit() to avoid root endpoints
                    if plan_id:
                        try:
                            js = "() => fetch('/api/dodaj_palete/{plan_id}', {{method:'POST', body: new URLSearchParams([['sekcja','Zasyp'], ['waga_palety','1000']]), credentials:'same-origin'}}).then(async r=>{{let t=await r.text(); return {{status: r.status, text: t}}}}).catch(e=>{{return {{status:'ERR', text: e.toString()}}}})".format(plan_id=plan_id)
                            res = page.evaluate(js)
                            logs.append('API add pallet response: ' + str(res))
                        except Exception as e:
                            logs.append('API add pallet failed: ' + str(e))
                    else:
                        page.evaluate('(function(){var i=document.querySelector("input[name=waga_palety]"); if(i && i.form) i.form.submit();})()')
                        logs.append('Submitted add pallet via form.submit() (no plan_id)')
            else:
                logs.append('Add pallet input not found in UI')
                # fallback: POST directly to /dodaj_palete/<plan_id>
                if plan_id:
                    try:
                        try:
                            # include sekcja param like the UI form does
                            js = "() => fetch('" + base + f"/api/dodaj_palete/{plan_id}', {{method:'POST', body: new URLSearchParams([['sekcja','Zasyp'], ['waga_palety','1000']]), credentials:'same-origin'}}).then(async r=>{{let t=await r.text(); return {{status:r.status, text:t}}}}).catch(e=>({{status:'ERR', text:e.toString()}}))"
                            res = page.evaluate(js)
                            logs.append('Fallback dodaj_palete POST: ' + str(res))
                        except Exception as e:
                            logs.append('Fallback dodaj_palete POST failed: ' + str(e))
                    except Exception as e:
                        logs.append('Fallback dodaj_palete failed: ' + str(e))
        except Exception as e:
            logs.append('Add pallet failed: ' + str(e))

        # final snapshot + traces
        try:
            page.screenshot(path='tools/playdoh_final.png', full_page=True)
            logs.append('Saved screenshot tools/playdoh_final.png')
        except Exception as e:
            logs.append('Screenshot failed: ' + str(e))

        try:
            ctx.close()
            browser.close()
        except Exception:
            pass

    with open(LOGS_FILE, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(logs))

    print('Wrote playdoh scenario logs to', LOGS_FILE)


if __name__ == '__main__':
    run()
