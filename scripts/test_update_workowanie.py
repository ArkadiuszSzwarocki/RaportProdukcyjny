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

r = client.post('/admin/ustawienia/workowanie_times/update', data={})
print('status', r.status_code)
print(r.get_data(as_text=True)[:400])
