from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Szukaj WSZYSTKICH ruchów PRODUKCJA (z pusty zbiornik)
cursor.execute('''
SELECT COUNT(*) as cnt_z_zbiornik, COUNT(CASE WHEN zbiornik IS NULL OR TRIM(zbiornik)='' THEN 1 END) as cnt_bez_zbiornika
FROM magazyn_ruch
WHERE typ_ruchu = 'PRODUKCJA'
''')

stats = cursor.fetchone()
print(f"PRODUKCJA ruch records:")
print(f"  - Z zbiornikiem: {stats['cnt_z_zbiornik']}")
print(f"  - BEZ zbiornika: {stats['cnt_bez_zbiornika']}")

# Pokaż te bez zbiornika
cursor.execute('''
SELECT r.id, s.nr_palety, r.ilosc, r.zbiornik, r.status, r.autor_data
FROM magazyn_ruch r
LEFT JOIN magazyn_surowce s ON r.surowiec_id = s.id
WHERE r.typ_ruchu = 'PRODUKCJA' AND (r.zbiornik IS NULL OR TRIM(r.zbiornik) = '')
ORDER BY r.autor_data DESC
LIMIT 5
''')

empty_ruch = cursor.fetchall()
print(f"\nRekordy BEZ zbiornika (ostatnie 5):")
for r in empty_ruch:
    print(f"  ID={r['id']}, paleta={r['nr_palety']}, zbiornik='{r['zbiornik']}', status={r['status']}")

conn.close()
