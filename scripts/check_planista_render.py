import sys, os
proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from app.core.factory import create_app
app = create_app(init_db=False)
client = app.test_client()
with client.session_transaction() as s:
    s['zalogowany'] = True
    s['rola'] = 'admin'
    s['login'] = 'test'

r = client.get('/planista?data=2026-02-07')
print('status', r.status_code)
data = r.get_data(as_text=True)
print('contains czyszczenie form?', 'name="tonaz"' in data and 'Czyszczenie' in data)
idx = data.find('Czyszczenie')
if idx!=-1:
    print(data[idx-120:idx+200])
else:
    print(data[:400])
