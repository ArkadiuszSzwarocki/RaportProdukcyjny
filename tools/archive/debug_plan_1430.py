import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection
from datetime import datetime, timedelta

PLAN_ID = 1430

conn = get_db_connection()
cur = conn.cursor()

print(f"Debugging plan_id={PLAN_ID}")
# fetch plan
cur.execute("SELECT id, produkt, data_planu, real_start FROM plan_produkcji WHERE id=%s", (PLAN_ID,))
plan = cur.fetchone()
print('plan:', plan)

# fetch all szarze for plan
cur.execute("SELECT id, data_dodania FROM szarze WHERE plan_id=%s ORDER BY data_dodania ASC", (PLAN_ID,))
szarze = cur.fetchall()
print('\nszarze:')
for s in szarze:
    print(s)

# fetch dosypki for plan (including potwierdzone and data_potwierdzenia)
cur.execute("SELECT id, szarza_id, potwierdzone, anulowana, data_potwierdzenia, data_zlecenia FROM dosypki WHERE plan_id=%s ORDER BY data_zlecenia ASC", (PLAN_ID,))
dosypki = cur.fetchall()
print('\ndosypki:')
for d in dosypki:
    print(d)

# find first szarza time
first_szarza_time = None
if szarze:
    first_szarza_time = szarze[0][1]

# find first confirmed dosypka that relates to first szarza
first_dosypka_confirmed_time = None
for d in dosypki:
    d_id, s_id, potw, anul, dp, dz = d
    if potw and not anul and s_id == (szarze[0][0] if szarze else None):
        first_dosypka_confirmed_time = dp
        break

print('\nfirst_szarza_time:', first_szarza_time)
print('first_dosypka_confirmed_time:', first_dosypka_confirmed_time)

mixing_minutes = 5.0
if first_dosypka_confirmed_time:
    dt = first_dosypka_confirmed_time
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    end_of_mixing = dt + timedelta(minutes=mixing_minutes)
    print('end_of_mixing:', end_of_mixing)
else:
    end_of_mixing = None

# find next szarza after the first
next_szarza = None
if szarze and len(szarze) > 1:
    next_szarza = szarze[1][1]
else:
    # try to find min szarze > first
    cur.execute("SELECT MIN(data_dodania) FROM szarze WHERE plan_id=%s AND data_dodania > (SELECT data_dodania FROM szarze WHERE plan_id=%s ORDER BY data_dodania ASC LIMIT 1)", (PLAN_ID, PLAN_ID))
    ns = cur.fetchone()
    next_szarza = ns[0] if ns else None

print('next_szarza_time:', next_szarza)

# compute wait
if end_of_mixing and next_szarza:
    ns_dt = next_szarza
    if isinstance(ns_dt, str):
        ns_dt = datetime.fromisoformat(ns_dt)
    delta = ns_dt - end_of_mixing
    minutes = delta.total_seconds() / 60.0
    print('wait_to_next_szarza (minutes):', minutes)
else:
    print('Insufficient data to compute wait_to_next_szarza')

conn.close()
