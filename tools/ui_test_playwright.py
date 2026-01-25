from playwright.sync_api import sync_playwright
import time

LOGS_FILE = 'tools/playwright_console.log'

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        logs = []

        page.on('console', lambda msg: logs.append(f"CONSOLE {msg.type}: {msg.text}"))
        page.on('pageerror', lambda exc: logs.append(f"PAGEERROR: {exc}"))

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

        # click + SZARŻA (first visible)
        try:
            # find button by scanning all buttons and matching text
            buttons = page.query_selector_all('button')
            target = None
            for b in buttons:
                try:
                    txt = (b.inner_text() or '').strip()
                except Exception:
                    txt = ''
                if '+ SZARŻA' in txt or 'SZARŻA' in txt:
                    target = b
                    break
            if not target:
                raise RuntimeError('SZARŻA button not found')
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
        time.sleep(1)
        browser.close()

        with open(LOGS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(logs))

        print('Wrote console logs to', LOGS_FILE)

if __name__ == '__main__':
    run()
