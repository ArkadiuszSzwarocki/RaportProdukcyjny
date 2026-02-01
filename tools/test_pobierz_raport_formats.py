import json
import sys
import os
from datetime import date

# make repo importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection

# Ensure a report exists for today
conn = get_db_connection()
cur = conn.cursor()
summary = {'data': date.today().isoformat(), 'sekcja': 'Zasyp', 'plany': [], 'pracownicy': [], 'notatki': 'test formats'}
cur.execute("INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json) VALUES (%s, %s, %s, %s, %s)", (date.today(), 'Zasyp', None, 'test formats', json.dumps(summary)))
conn.commit()
cur.execute("SELECT id FROM raporty_koncowe WHERE data_raportu=%s ORDER BY id DESC LIMIT 1", (date.today(),))
row = cur.fetchone()
print('Inserted raport id:', row[0] if row else 'none')
conn.close()

from app import app

formats = ['excel', 'pdf']
for fmt in formats:
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['rola'] = 'admin'
            sess['pracownik_id'] = None
        data_str = date.today().isoformat()
        print('\nRequesting format =', fmt)
        resp = c.get(f"/api/pobierz-raport?format={fmt}&data={data_str}")
        print('status_code:', resp.status_code)
        print('headers:', {k:v for k,v in resp.headers.items() if k.lower().startswith(('content-type','content-disposition'))})
        # show small preview if binary
        if resp.status_code == 200:
            print('body preview (first 200 bytes):', resp.data[:200])
        else:
            print('response body (text):', resp.data.decode('utf-8', errors='replace')[:400])
