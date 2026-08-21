import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection
import datetime

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

plan_id = 222
cursor.execute("SELECT * FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
plan = cursor.fetchone()

real_start = plan['real_start']
real_stop = plan['real_stop'] or datetime.datetime.now()

materials = []

# 1. Fetch active tank allocations at start time
q_active_start = """
    SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.nr_partii, r.zbiornik, r.autor_data, r.ilosc
    FROM magazyn_agro_ruch r
    LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
    WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE'
      AND r.autor_data <= %s
      AND r.zbiornik IS NOT NULL AND TRIM(r.zbiornik) <> ''
      AND NOT EXISTS (
          SELECT 1 FROM magazyn_agro_ruch z 
          WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT' 
            AND z.autor_data <= %s
      )
"""
cursor.execute(q_active_start, (real_start, real_start))
rows = cursor.fetchall()
for r in rows:
    # Check if replaced before start_time
    cursor.execute(
        "SELECT id FROM magazyn_agro_ruch WHERE typ_ruchu = 'PRODUKCJA' AND status = 'POTWIERDZONE' AND zbiornik = %s AND id > %s AND autor_data <= %s",
        (r['zbiornik'], r['ruch_id'], real_start)
    )
    if not cursor.fetchone():
        materials.append({
            'surowiec_id': r['surowiec_id'],
            'surowiec_nazwa': r['surowiec_nazwa'] or 'Surowiec',
            'nr_partii': r['nr_partii'] or 'Brak',
            'zuzycie': r['ilosc'],
            'autor_data': r['autor_data'],
            'zbiornik': r['zbiornik'],
            'typ_ruchu': 'ZASYP (ZBIORNIK)'
        })

# 2. Fetch tank allocations loaded during the plan
q_during = """
    SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.nr_partii, r.zbiornik, r.autor_data, r.ilosc
    FROM magazyn_agro_ruch r
    LEFT JOIN magazyn_agro_surowce s ON r.surowiec_id = s.id
    WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE'
      AND r.autor_data > %s AND r.autor_data <= %s
      AND r.zbiornik IS NOT NULL AND TRIM(r.zbiornik) <> ''
"""
cursor.execute(q_during, (real_start, real_stop))
rows = cursor.fetchall()
for r in rows:
    materials.append({
        'surowiec_id': r['surowiec_id'],
        'surowiec_nazwa': r['surowiec_nazwa'] or 'Surowiec',
        'nr_partii': r['nr_partii'] or 'Brak',
        'zuzycie': r['ilosc'],
        'autor_data': r['autor_data'],
        'zbiornik': r['zbiornik'],
        'typ_ruchu': 'ZASYP (ZBIORNIK)'
    })

# 3. Fetch dosypki
q_dosypki = """
    SELECT d.id, d.nazwa as surowiec_nazwa, d.kg as zuzycie, d.data_potwierdzenia as autor_data, 'DOSYPKA' as typ_ruchu
    FROM dosypki_agro d
    WHERE d.plan_id = %s AND d.potwierdzone = 1 AND d.anulowana = 0
"""
cursor.execute(q_dosypki, (plan_id,))
rows = cursor.fetchall()
for r in rows:
    materials.append({
        'surowiec_id': None,
        'surowiec_nazwa': r['surowiec_nazwa'],
        'nr_partii': 'Dosypka manualna',
        'zuzycie': -r['zuzycie'],
        'autor_data': r['autor_data'],
        'zbiornik': 'Dosypka',
        'typ_ruchu': 'DOSYPKA'
    })

print(f"Total materials found: {len(materials)}")
for m in materials:
    print(m)

cursor.close()
conn.close()
