#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.abspath('.'))
import importlib.machinery
import importlib.util

# Load top-level app.py (avoids package 'app' conflict)
loader = importlib.machinery.SourceFileLoader('app_module', os.path.join(os.path.dirname(__file__), '..', 'app.py'))
spec = importlib.util.spec_from_loader(loader.name, loader)
app_module = importlib.util.module_from_spec(spec)
loader.exec_module(app_module)
flask_app = getattr(app_module, 'app')

def main():
    with flask_app.test_client() as client:
        # set session 'rola' to laborant
        with client.session_transaction() as sess:
            sess['rola'] = 'laborant'
            sess['username'] = 'HelleAnd'
            sess['zalogowany'] = True
        # request Zasyp sekcja
        resp = client.get('/?sekcja=Zasyp')
        html = resp.get_data(as_text=True)
        found = '+ DOSYPKA' in html
        print('Status:', resp.status_code)
        print('Contains + DOSYPKA:', found)
        if not found:
            # for debugging, print surrounding fragment
            idx = html.find('+ DOSYPKA')
            if idx != -1:
                print(html[max(0, idx-200):idx+200])
        # optionally, save html to file for manual inspection
        try:
            with open('test_output_dosypka.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print('Saved HTML to test_output_dosypka.html')
        except Exception as e:
            print('Could not save HTML:', e)

if __name__ == '__main__':
    main()
