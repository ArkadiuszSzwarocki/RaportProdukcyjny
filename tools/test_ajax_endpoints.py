import requests
import time
import sys
import os
# Ensure project root is on sys.path so we can import `db` and app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

base = 'http://127.0.0.1:8082'
session = requests.Session()
prod = 'TEST_AJAX_' + time.strftime('%Y%m%d%H%M%S')
try:
    print('Logging in as planista...')
    r = session.post(base + '/login', data={'login':'planista','haslo':'planista123'}, allow_redirects=True, timeout=10)
    print('Login status:', r.status_code)

    print('Adding plan', prod)
    r = session.post(base + '/dodaj_plan', data={'produkt': prod, 'tonaz': '10', 'data_planu': '2026-01-28', 'sekcja': 'Zasyp'}, allow_redirects=True, timeout=10)
    print('Add plan status:', r.status_code)

    # give server a moment
    time.sleep(1)

    conn = db.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM plan_produkcji WHERE produkt=%s ORDER BY id DESC LIMIT 1", (prod,))
    row = cur.fetchone()
    if not row:
        print('Failed to find created plan in DB')
        sys.exit(2)
    pid = int(row[0])
    print('Created plan id=', pid)

    print('Calling move endpoint (up)...')
    r = session.post(base + '/api/przesun_zlecenie_ajax', json={'id': pid, 'kierunek':'gora', 'data':'2026-01-28'}, timeout=10)
    try:
        print('Move response:', r.status_code, r.json())
    except Exception:
        print('Move raw:', r.status_code, r.text)

    print('Calling delete endpoint...')
    r = session.post(base + f'/api/usun_plan_ajax/{pid}', timeout=10)
    try:
        print('Delete response:', r.status_code, r.json())
    except Exception:
        print('Delete raw:', r.status_code, r.text)

    conn.close()
except Exception as e:
    print('Test failed:', e)
    sys.exit(1)
else:
    print('Test finished')
    sys.exit(0)
