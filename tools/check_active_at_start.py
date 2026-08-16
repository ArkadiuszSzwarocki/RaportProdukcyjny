import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

start_time = '2026-07-06 14:12:23'

# We query the active surowce in each tank at start_time.
# To do this, we find the latest PRODUKCJA movement for each tank before start_time,
# and check if it was not returned/exhausted before start_time.
# Actually, let's just get the latest PRODUKCJA move for each tank before start_time.
q = """
    SELECT r.id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, r.zbiornik, r.autor_data, r.ilosc
    FROM magazyn_agro_ruch r
    LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
    WHERE r.id IN (
        SELECT MAX(id)
        FROM magazyn_agro_ruch
        WHERE typ_ruchu = 'PRODUKCJA' AND status = 'POTWIERDZONE' AND autor_data <= %s
        GROUP BY zbiornik
    )
    ORDER BY r.zbiornik
"""
cursor.execute(q, (start_time,))
rows = cursor.fetchall()
print("--- Connected surowce at start time ---")
for r in rows:
    # Check if this pallet was returned before start_time
    cursor.execute(
        "SELECT SUM(ilosc) FROM magazyn_agro_ruch WHERE ruch_zrodlowy_id = %s AND typ_ruchu = 'ZWROT' AND autor_data <= %s",
        (r['id'], start_time)
    )
    zwrot = cursor.fetchone()
    zwrot_val = float(list(zwrot.values())[0] or 0)
    pobrana = abs(float(r['ilosc'] or 0))
    stan = pobrana - zwrot_val
    if stan > 0:
        print(f"Tank: {r['zbiornik']} | Material: {r['surowiec_nazwa']} | PalletID: {r['surowiec_id']} | Stan: {stan}kg | Linked: {r['autor_data']}")

cursor.close()
conn.close()
