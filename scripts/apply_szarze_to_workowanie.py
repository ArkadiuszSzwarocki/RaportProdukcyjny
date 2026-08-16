import sys
from app.db import get_db_connection, log_plan_history

if len(sys.argv) < 2:
    print('Usage: python apply_szarze_to_workowanie.py <zasyp_plan_id>')
    sys.exit(1)

zasyp_plan_id = int(sys.argv[1])
conn = get_db_connection()
cur = conn.cursor()

# sum all szarze for this zasyp plan
cur.execute("SELECT COALESCE(SUM(waga),0) FROM szarze WHERE plan_id=%s", (zasyp_plan_id,))
sum_szarze = cur.fetchone()[0] or 0
print(f'Sum szarze for zasyp {zasyp_plan_id}: {sum_szarze}')

# find workowanie linked to this zasyp
cur.execute("SELECT id, tonaz FROM plan_produkcji WHERE zasyp_id=%s AND sekcja='Workowanie' LIMIT 1", (zasyp_plan_id,))
row = cur.fetchone()
if row:
    work_id, w_tonaz = row[0], row[1] or 0
    new_tonaz = (w_tonaz or 0) + sum_szarze
    cur.execute("UPDATE plan_produkcji SET tonaz=%s WHERE id=%s", (new_tonaz, work_id))
    conn.commit()
    print(f'Updated Workowanie id={work_id}: tonaz {w_tonaz} -> {new_tonaz}')
    try:
        log_plan_history(work_id, 'auto-szarza-apply', f'Applied szarze sum {sum_szarze}', user_login='system')
    except Exception:
        pass
else:
    # find by product/date of zasyp
    cur.execute("SELECT data_planu, produkt, typ_produkcji FROM plan_produkcji WHERE id=%s", (zasyp_plan_id,))
    zas = cur.fetchone()
    if not zas:
        print('Zasyp plan not found')
        conn.close()
        sys.exit(1)
    data_planu, produkt, typ = zas[0], zas[1], zas[2]
    # create new workowanie
    cur.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s AND sekcja='Workowanie'", (data_planu,))
    res = cur.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cur.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (data_planu, produkt, sum_szarze, 'zaplanowane', 'Workowanie', nk, typ, 0, zasyp_plan_id))
    conn.commit()
    new_id = cur.lastrowid if hasattr(cur, 'lastrowid') else None
    print(f'Created Workowanie id={new_id} with tonaz={sum_szarze}')
    try:
        log_plan_history(new_id, 'auto-szarza-apply', f'Created Workowanie and applied szarze sum {sum_szarze}', user_login='system')
    except Exception:
        pass

conn.close()
