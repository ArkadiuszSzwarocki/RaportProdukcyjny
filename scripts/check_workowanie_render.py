import sys
import os
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

r = client.get('/admin/ustawienia/workowanie_times')
print('status', r.status_code)
data = r.get_data(as_text=True)
print('contains timings-table-body?', 'timings-table-body' in data)
idx = data.find('timings-table-body')
if idx != -1:
    print(data[idx:idx+800])
else:
    print(data[:800])
