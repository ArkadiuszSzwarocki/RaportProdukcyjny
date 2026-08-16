import os
import json
from datetime import date

# make repo importable
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import get_db_connection
from app import app


def ensure_report_in_db(target_date=None):
    if target_date is None:
        target_date = date.today()
    conn = get_db_connection()
    cur = conn.cursor()
    summary = {'data': target_date.isoformat(), 'sekcja': 'Zasyp', 'plany': [], 'pracownicy': [], 'notatki': 'save formats'}
    cur.execute("INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json) VALUES (%s, %s, %s, %s, %s)", (target_date, 'Zasyp', None, 'save formats', json.dumps(summary)))
    conn.commit()
    cur.execute("SELECT id FROM raporty_koncowe WHERE data_raportu=%s ORDER BY id DESC LIMIT 1", (target_date,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else None


def save_reports(target_date=None):
    if target_date is None:
        target_date = date.today()
    # ensure raport exists
    rid = ensure_report_in_db(target_date)
    print('Inserted raport id:', rid)

    out_dir = os.path.join(os.getcwd(), 'raporty')
    os.makedirs(out_dir, exist_ok=True)

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['rola'] = 'admin'
            sess['pracownik_id'] = None

        formats = [('email', 'txt'), ('excel', 'xlsx'), ('pdf', 'pdf')]
        for fmt, ext in formats:
            print('Requesting', fmt)
            resp = c.get(f"/api/pobierz-raport?format={fmt}&data={target_date.isoformat()}")
            if resp.status_code == 200:
                filename = f'Raport_{target_date.isoformat()}.{ext}'
                path = os.path.join(out_dir, filename)
                with open(path, 'wb') as fh:
                    fh.write(resp.data)
                print('Saved', path)
            else:
                print('Failed to fetch', fmt, 'status=', resp.status_code)


if __name__ == '__main__':
    save_reports()
