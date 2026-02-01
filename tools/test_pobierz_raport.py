import json
import sys
import os
from datetime import date

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection

# Insert a minimal raport into DB for today
conn = get_db_connection()
cur = conn.cursor()
summary = {'data': date.today().isoformat(), 'sekcja': 'Zasyp', 'plany': [], 'pracownicy': [], 'notatki': 'test'}
cur.execute("INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json) VALUES (%s, %s, %s, %s, %s)", (date.today(), 'Zasyp', None, 'test', json.dumps(summary)))
conn.commit()
inserted_id = None
try:
    inserted_id = cur.lastrowid if hasattr(cur, 'lastrowid') else None
except Exception:
    pass
cur.execute("SELECT id FROM raporty_koncowe WHERE data_raportu=%s ORDER BY id DESC LIMIT 1", (date.today(),))
row = cur.fetchone()
print('Inserted raport id:', row[0] if row else inserted_id)
conn.close()

# Use Flask test client to GET the download endpoint as admin
from app import app
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'
        sess['pracownik_id'] = None
    data_str = date.today().isoformat()
    resp = c.get(f"/api/pobierz-raport?format=email&data={data_str}")
    print('status_code:', resp.status_code)
    print('content-disposition:', resp.headers.get('Content-Disposition'))
    print('body preview:', resp.data[:400].decode('utf-8', errors='replace'))
