import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Search from beginning of July 6th to now (July 7th evening)
q = """
    SELECT r.id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, r.zbiornik, r.autor_data, r.ilosc, r.autor_login, r.typ_ruchu
    FROM magazyn_agro_ruch r
    LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
    WHERE r.status = 'POTWIERDZONE'
      AND r.autor_data >= '2026-07-06 00:00:00' AND r.autor_data <= '2026-07-07 21:00:00'
    ORDER BY r.autor_data
"""
cursor.execute(q)
rows = cursor.fetchall()
print("--- ALL moves from 2026-07-06 00:00 to 2026-07-07 21:00 ---")
for r in rows:
    # Check if surowiec details can be found in magazyn_surowce
    if not r['surowiec_nazwa']:
        cursor.execute("SELECT nazwa FROM magazyn_surowce WHERE id = %s", (r['surowiec_id'],))
        row_s = cursor.fetchone()
        if row_s:
            r['surowiec_nazwa'] = row_s['nazwa']
            
    print(f"Time: {r['autor_data']} | Type: {r['typ_ruchu']} | Tank: {r['zbiornik']} | Material: {r['surowiec_nazwa']} | PalletID: {r['surowiec_id']} | Qty: {r['ilosc']}kg | User: {r['autor_login']}")

cursor.close()
conn.close()
