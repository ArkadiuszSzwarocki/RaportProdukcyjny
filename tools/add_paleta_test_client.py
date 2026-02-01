import os
import sys
import importlib

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
mod = importlib.import_module('app')
flask_app = getattr(mod, 'app')

with flask_app.test_client() as c:
    # set session to logged in admin
    with c.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'

    plan_id = 329
    print('Posting paleta for plan', plan_id)
    r = c.post(f'/api/dodaj_palete/{plan_id}', data={'waga_palety': '25', 'typ_produkcji': 'standard', 'sekcja': 'Workowanie'}, follow_redirects=True)
    print('POST status', r.status_code)
    # Now fetch bufor
    rb = c.get('/api/bufor')
    print('bufor status', rb.status_code)
    try:
        j = rb.get_json()
        print('bufor entries count', len(j.get('bufor', [])))
        # print the entry for our plan if present
        for e in j.get('bufor', []):
            if e.get('id') == plan_id:
                print('FOUND plan in bufor:', e)
    except Exception:
        print('bufor text:', rb.data[:400])
