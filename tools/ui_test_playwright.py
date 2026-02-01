import os
from playwright.sync_api import sync_playwright
import time

LOGS_FILE = 'tools/playwright_console.log'

def run():
    # Run headed with slow_mo to observe UI; set headless=False for interactive debugging
    # allow running in headless mode by setting env var PLAYWRIGHT_HEADLESS=1
    headless_env = os.environ.get('PLAYWRIGHT_HEADLESS', '1')
    headless = False if headless_env in ('0', 'false', 'False') else True
    slow_mo = int(os.environ.get('PLAYWRIGHT_SLOW_MO', '0'))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        # create context so we can capture a Playwright trace
        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        logs = []

        page.on('console', lambda msg: logs.append(f"CONSOLE {msg.type}: {msg.text}"))
        page.on('pageerror', lambda exc: logs.append(f"PAGEERROR: {exc}"))
        # capture network requests/responses
        def on_request(request):
            try:
                logs.append(f"REQUEST {request.method} {request.url}")
            except Exception:
                pass
        def on_response(response):
            try:
                logs.append(f"RESPONSE {response.status} {response.url}")
                # save HTML body for Zasyp page responses for inspection
                try:
                    if '/?sekcja=Zasyp' in response.url or (response.url.endswith('/') and response.request.method == 'GET'):
                        try:
                            txt = response.text()
                            if txt and len(txt) < 500000:
                                with open('tools/last_zasyp_response.html', 'w', encoding='utf-8') as fh:
                                    fh.write(txt)
                                logs.append('Saved Zasyp response body to tools/last_zasyp_response.html')
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass
        page.on('request', on_request)
        page.on('response', on_response)

        # login
        page.goto('http://localhost:8082/login')
        try:
            page.fill('input[name=login]', 'admin')
            page.fill('input[name=haslo]', 'masterkey')
            page.click('button[type=submit]')
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception as e:
            logs.append('Login failed: ' + str(e))

        # inject wrapper
        wrapper = r"""
        (function(){
          const orig = window.openModal;
          window.openModal = function(id){
            try{
              console.log('[trace-wrapper] openModal called id=', id, 'skip_open_stop=', sessionStorage.getItem('skip_open_stop'));
              console.trace('[trace-wrapper] call stack for openModal');
            }catch(e){console.error(e)}
            return orig.apply(this, arguments);
          };
          console.log('[trace-wrapper] wrapper installed');
        })();
        """
        page.evaluate(wrapper)

        # ensure we are on the production dashboard for Zasyp (not the global overview)
        try:
            page.goto('http://localhost:8082/?sekcja=Zasyp', timeout=10000)
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            pass

        # click + SZARŻA (first visible)
        try:
            # collect DOM diagnostics to help debug missing SZARZA button
            try:
                diag = page.evaluate(r"""
                () => {
                    try{
                        const els = Array.from(document.querySelectorAll('button, a, [role="button"], input[type=submit]')).map(el=>{
                            const s = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
                            return {text:(el.innerText||'').trim().slice(0,120), tag:el.tagName, visible: (s.display!=='none' && s.visibility!=='hidden' && el.offsetParent!==null), rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}, outer: (el.outerHTML||'').slice(0,500)};
                        });
                        const headers = Array.from(document.querySelectorAll('h4')).map(h=>({text:(h.innerText||'').trim(), outer:(h.outerHTML||'').slice(0,500)}));
                        const zasypHeader = headers.find(h=>h.text && h.text.indexOf('Zasyp')!==-1);
                        const overlay = document.getElementById('modalOverlay');
                        const stops = Array.from(document.querySelectorAll('[id^="stop-"]')).map(e=>({id:e.id, display:getComputedStyle(e).display}));
                        return JSON.stringify({els, headers, zasypHeader, overlayPresent: !!overlay, overlayDisplay: overlay?getComputedStyle(overlay).display:null, stops, cookies: document.cookie});
                    }catch(e){return 'ERR:'+e.toString();}
                }
                """)
                logs.append('DIAG_DOM: ' + (diag or ''))
            except Exception as e:
                logs.append('DIAG_DOM_FAILED: ' + str(e))

            # find clickable element by scanning buttons, anchors and other clickable elements
            candidates = page.query_selector_all('button, a, [role="button"], input[type=submit]')
            target = None
            for el in candidates:
                try:
                    txt = (el.inner_text() or '').strip()
                except Exception:
                    txt = ''
                if '+ SZARŻA' in txt or 'SZARŻA' in txt:
                    target = el
                    break
            # If no SZARZA candidate found, try to create a minimal plan via POST to /api/dodaj_plan
            if not target:
                try:
                    page.evaluate("""
                        (function(){
                            try{
                                var fd = new URLSearchParams();
                                fd.append('produkt','TEST Produkt');
                                fd.append('tonaz','100');
                                fd.append('sekcja','Zasyp');
                                return fetch('/api/dodaj_plan', {method:'POST', body: fd, credentials: 'same-origin'}).then(r => r.text()).catch(e => 'ERR:'+e.toString());
                            }catch(e){return 'ERR:'+e.toString();}
                        })()
                    """)
                    time.sleep(0.5)
                    # navigate explicitly to production dashboard Zasyp after creating plan
                    try:
                        page.goto('http://localhost:8082/?sekcja=Zasyp&data=2026-01-30', timeout=10000)
                        page.wait_for_load_state('networkidle', timeout=5000)
                    except Exception:
                        try:
                            page.reload()
                        except Exception:
                            pass
                    time.sleep(0.5)
                    # re-scan candidates
                    candidates = page.query_selector_all('button, a, [role="button"], input[type=submit]')
                    for el in candidates:
                        try:
                            txt = (el.inner_text() or '').strip()
                        except Exception:
                            txt = ''
                        if '+ SZARŻA' in txt or 'SZARŻA' in txt:
                            target = el
                            break
                except Exception as e:
                    logs.append('Auto-create plan failed: ' + str(e))

            if not target:
                    # save page snapshot for debugging
                    try:
                        with open(LOGS_FILE + '.html', 'w', encoding='utf-8') as fh:
                            fh.write(page.content())
                        logs.append('SZARZA not found - wrote page snapshot to ' + LOGS_FILE + '.html')
                    except Exception as e:
                        logs.append('Failed to write page snapshot: ' + str(e))
                    raise RuntimeError('SZARŻA element not found')
            target.click()
            time.sleep(0.5)
            # set skip flag so any stop-* openModal calls are suppressed
            try:
                page.evaluate("sessionStorage.setItem('skip_open_stop','1')")
            except Exception:
                pass
            # ensure overlay and any stop modals are hidden to avoid intercepting clicks
            try:
                page.evaluate("document.getElementById('modalOverlay').style.display='none'; document.querySelectorAll('[id^=stop-]').forEach(el=>el.style.display='none')")
            except Exception:
                pass
            # fill visible waga_palety
            el = page.query_selector("input[name=waga_palety]")
            if el:
                el.fill('1000')
            # submit the first visible DODAJ button inside a form
            forms = page.query_selector_all('form')
            submitted = False
            for f in forms:
                try:
                    btn = f.query_selector("button")
                    if btn and ('DODAJ' in (btn.inner_text() or '').upper()):
                        btn.click()
                        submitted = True
                        break
                except Exception:
                    continue
            if not submitted:
                # fallback: submit the first visible form programmatically
                try:
                    page.evaluate("(function(){var forms=document.querySelectorAll('form'); for(var i=0;i<forms.length;i++){var s=getComputedStyle(forms[i].parentElement||forms[i]); if(s && s.display!='none'){forms[i].submit(); return true;}} return false; })()")
                    submitted = True
                except Exception:
                    # fallback: click any button with DODAJ text
                    for b in page.query_selector_all('button'):
                        if 'DODAJ' in (b.inner_text() or '').upper():
                            b.click()
                            submitted = True
                            break
            if not submitted:
                raise RuntimeError('DODAJ submit button not found')
            page.wait_for_load_state('networkidle', timeout=5000)
        except Exception as e:
            logs.append('Interaction failed: ' + str(e))

        # give some time for any async console logs
        time.sleep(2)
        try:
            page.screenshot(path='tools/playwright_snapshot.png', full_page=True)
            logs.append('Saved page screenshot to tools/playwright_snapshot.png')
        except Exception as e:
            logs.append('Screenshot failed: ' + str(e))
        # stop tracing and save
        try:
            context.tracing.stop(path='tools/playwright_trace.zip')
            logs.append('Saved Playwright trace to tools/playwright_trace.zip')
        except Exception as e:
            logs.append('Trace stop failed: ' + str(e))
        # write network log copy
        try:
            with open('tools/playwright_network.log', 'w', encoding='utf-8') as nf:
                for L in logs:
                    if L.startswith('REQUEST') or L.startswith('RESPONSE'):
                        nf.write(L + '\n')
            logs.append('Saved network log to tools/playwright_network.log')
        except Exception:
            pass
        browser.close()

        with open(LOGS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(logs))

        print('Wrote console logs to', LOGS_FILE)

if __name__ == '__main__':
    run()
