# Test script: attempt to start the Workowanie plan corresponding to earliest-closed Zasyp on given date
import os
from app.core.factory import create_app
from app.db import get_db_connection

DATE = os.environ.get('TEST_DATE', '2026-02-08')

app = create_app(init_db=False)
app.testing = True

with app.app_context():
    conn = get_db_connection()
    cur = conn.cursor()
    # find earliest closed Zasyp product for DATE
    cur.execute("SELECT id, produkt FROM plan_produkcji WHERE sekcja='Zasyp' AND status='zakonczone' AND DATE(data_planu)=%s AND real_stop IS NOT NULL ORDER BY real_stop ASC LIMIT 1", (DATE,))
    row = cur.fetchone()
    if not row:
        print('No closed Zasyp found for date', DATE)
        conn.close()
        raise SystemExit(1)
    zasyp_id, produkt = row[0], row[1]
    print('Earliest closed Zasyp:', zasyp_id, produkt)

    # find Workowanie plan with same produkt and date
    cur.execute("SELECT id FROM plan_produkcji WHERE sekcja='Workowanie' AND produkt=%s AND DATE(data_planu)=%s", (produkt, DATE))
    r2 = cur.fetchone()
    if not r2:
        print('No matching Workowanie plan found for produkt', produkt)
        conn.close()
        raise SystemExit(1)
    work_id = r2[0]
    print('Found Workowanie plan id:', work_id)
    conn.close()

# Use Flask test client to simulate a logged-in non-planista user
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'testuser'
        sess['rola'] = 'operator'
    print('\n-> Sending POST to start_zlecenie for id', work_id)
    resp = client.post(f'/start_zlecenie/{work_id}', follow_redirects=True)
    print('Response status:', resp.status)
    # Print body snippet
    data = resp.get_data(as_text=True)
    print('Response body snippet:\n', data[:1000])

# Dump recent KOLEJKA log lines
log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'app.log')
if os.path.exists(log_path):
    print('\n== Last [KOLEJKA] lines from logs/app.log ==')
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for ln in lines[-500:]:
        if '[KOLEJKA]' in ln:
            print(ln.strip())
else:
    print('logs/app.log not found')
