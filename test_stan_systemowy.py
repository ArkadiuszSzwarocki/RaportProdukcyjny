from app.db import get_db_connection, get_table_name

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Sprawdź stan systemowy dla każdego PRODUKCJA ruchu
cursor.execute('''
SELECT 
    r.id as ruch_id,
    s.nr_palety,
    s.nazwa,
    r.zbiornik,
    ABS(r.ilosc) as ilosc_pobrana,
    COALESCE((SELECT SUM(z.ilosc) FROM magazyn_ruch z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as ilosc_zwrocona,
    COALESCE((SELECT SUM(k.ilosc) FROM magazyn_ruch k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as ilosc_korekta
FROM magazyn_ruch r
LEFT JOIN magazyn_surowce s ON r.surowiec_id = s.id
WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE'
ORDER BY r.autor_data DESC
LIMIT 10
''')

ruchy = cursor.fetchall()
print(f'Stan systemowy dla ruchow:')
for r in ruchy:
    pobrana = float(r['ilosc_pobrana'] or 0)
    zwrocona = float(r['ilosc_zwrocona'] or 0)
    korekta = float(r['ilosc_korekta'] or 0)
    stan_systemowy = round(pobrana - zwrocona + korekta, 2)
    
    will_show = "POKAZE SIE" if stan_systemowy > 0 else "BEDZIE FILTROWANE"
    print(f"  {r['ruch_id']}: {r['nr_palety']} na {r['zbiornik']}")
    print(f"      pobrana={pobrana}, zwrocona={zwrocona}, korekta={korekta}")
    print(f"      stan_systemowy={stan_systemowy} {will_show}")

conn.close()
