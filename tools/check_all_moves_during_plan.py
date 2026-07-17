import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

start_time = '2026-07-06 14:12:23'
end_time = '2026-07-07 13:23:42'

q = """
    SELECT r.id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, r.zbiornik, r.autor_data, r.ilosc, r.autor_login, r.typ_ruchu
    FROM magazyn_agro_ruch r
    LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
    WHERE r.status = 'POTWIERDZONE'
      AND r.autor_data >= %s AND r.autor_data <= %s
    ORDER BY r.autor_data
"""
cursor.execute(q, (start_time, end_time))
rows = cursor.fetchall()
print("--- ALL movements during plan ---")
for r in rows:
    print(f"Time: {r['autor_data']} | Type: {r['typ_ruchu']} | Tank: {r['zbiornik']} | Material: {r['surowiec_nazwa']} | PalletID: {r['surowiec_id']} | Qty: {r['ilosc']}kg | User: {r['autor_login']}")

cursor.close()
conn.close()
