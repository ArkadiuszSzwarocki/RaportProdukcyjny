import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection
from datetime import datetime, timedelta
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--date', default='2026-03-12')
args = parser.parse_args()
qdate = datetime.strptime(args.date, '%Y-%m-%d').date()
start = qdate
end = qdate + timedelta(days=1)

conn = get_db_connection()
cur = conn.cursor()
print('Querying plans for', start, '->', end)
cur.execute("SELECT id, produkt, data_planu, real_start, status FROM plan_produkcji WHERE sekcja='Zasyp' AND data_planu >= %s AND data_planu < %s ORDER BY data_planu, kolejnosc", (start, end))
plans = cur.fetchall()
print('Found plans:', len(plans))
for p in plans:
    print('PLAN', p)
    plan_id = p[0]
    # szarze
    cur.execute("SELECT id, waga, data_dodania, pracownik_id, status FROM szarze WHERE plan_id=%s ORDER BY data_dodania", (plan_id,))
    szarze = cur.fetchall()
    print('  szarze count:', len(szarze))
    for s in szarze[:5]:
        print('   SZARZA', s)
    # dosypki
    cur.execute("SELECT id, nazwa, kg, data_zlecenia, potwierdzone, data_potwierdzenia, anulowana FROM dosypki WHERE plan_id=%s ORDER BY data_zlecenia", (plan_id,))
    dos = cur.fetchall()
    print('  dosypki count:', len(dos))
    for d in dos[:5]:
        print('   DOSYPKA', d)

conn.close()
