from app.db import get_db_connection, get_table_name

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Szukaj ostatnich ruchów typu PRODUKCJA
cursor.execute('''
SELECT r.id, r.surowiec_id, s.nr_palety, s.nazwa, r.typ_ruchu, r.zbiornik, r.ilosc, r.status, r.autor_data
FROM magazyn_ruch r
LEFT JOIN magazyn_surowce s ON r.surowiec_id = s.id
WHERE r.typ_ruchu = 'PRODUKCJA'
ORDER BY r.autor_data DESC
LIMIT 10
''')

ruchy = cursor.fetchall()
print(f'Ostatnie ruchy PRODUKCJA ({len(ruchy)}):')
for r in ruchy:
    print(f"  ID={r['id']}, nr_palety={r['nr_palety']}, zbiornik='{r['zbiornik']}' (len={len(str(r['zbiornik'] or ''))}), status={r['status']}, ilosc={r['ilosc']}")
    if not r['zbiornik'] or str(r['zbiornik']).strip() == '':
        print(f"    ⚠️ ZBIORNIK IS EMPTY/NULL!")

conn.close()
