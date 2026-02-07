import sys, os
sys.path.insert(0, os.path.abspath('.'))
from app import app
from db import get_db_connection

pal_id = 137
print('Testing paleta id=', pal_id)
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'admin'
        sess['rola'] = 'admin'
    r = client.post(f'/api/potwierdz_palete/{pal_id}')
    print('Response status:', r.status_code)
    print('Response data:', r.get_data(as_text=True))

# Verify DB
conn = get_db_connection()
c = conn.cursor()
c.execute('SELECT id, status FROM palety_workowanie WHERE id = %s', (pal_id,))
row = c.fetchone()
print('DB row for id=%s: %s' % (pal_id, row))
c.close()
conn.close()
