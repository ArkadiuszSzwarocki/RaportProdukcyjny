import sys, os
sys.path.insert(0, os.path.abspath('.'))
from app import app
from db import get_db_connection

print('Using app:', app)
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'admin'
        sess['rola'] = 'admin'
    r = client.post('/api/potwierdz_palete/1')
    print('Response status:', r.status_code)
    try:
        print('Response data:', r.get_data(as_text=True))
    except Exception:
        pass

# Verify DB
conn = get_db_connection()
c = conn.cursor()
c.execute('SELECT id, status FROM palety_workowanie WHERE id = %s', (1,))
row = c.fetchone()
print('DB row for id=1:', row)
c.close()
conn.close()
