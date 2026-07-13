import sys
import os
sys.path.insert(0, 'a:/GitHub/RaportProdukcyjny')
from dotenv import load_dotenv
import mysql.connector

load_dotenv('a:/GitHub/RaportProdukcyjny/.env')

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database='biblioteka'
)
cur = conn.cursor(dictionary=True)

stacja = 'BB19'
where_clauses = ["r.typ_ruchu IN ('PRODUKCJA', 'PRZESUNIECIE', 'dosypka', 'bufor_zasyp', 'cleaning', 'PRZYJECIE', 'WYDANIE_PRZESUNIECIE', 'KOREKTA', 'INWENTARYZACJA')"]
where_params = []
where_clauses.append("(r.zbiornik LIKE %s OR r.lokalizacja LIKE %s OR r.komentarz LIKE %s OR r.komentarz LIKE %s)")
where_params.extend([f"%{stacja}%", f"%{stacja}%", f"%do {stacja}%", f"%-> {stacja}%"])

where_sql = " AND ".join(where_clauses)
query = f"""
    SELECT 
        r.id, 
        r.surowiec_nazwa, 
        r.typ_ruchu, 
        r.ilosc, 
        r.ilosc_po, 
        r.lokalizacja, 
        r.zbiornik, 
        r.autor_login, 
        r.created_at AS created_at, 
        r.komentarz,
        pal.nr_palety,
        pal.nazwa AS pal_nazwa
    FROM magazyn_ruch r
    LEFT JOIN magazyn_surowce pal ON r.surowiec_id = pal.id
    WHERE {where_sql}
    ORDER BY r.created_at DESC
    LIMIT 10
"""
cur.execute(query, where_params)
data = []
for r in cur.fetchall():
    stacja_val = r.get('zbiornik') or r.get('lokalizacja')
    if not stacja_val and r.get('komentarz'):
        kom = r.get('komentarz')
        if 'do ' in kom:
            parts = kom.split('do ')
            if len(parts) > 1:
                stacja_val = parts[1].strip()
        elif '-> ' in kom:
            parts = kom.split('-> ')
            if len(parts) > 1:
                stacja_val = parts[1].strip()
    stacja_val = stacja_val or '-'
    data.append({
        'id': r['id'],
        'data': r['created_at'].strftime('%Y-%m-%d %H:%M') if r.get('created_at') else '-',
        'surowiec': r['surowiec_nazwa'],
        'ilosc': f"{r['ilosc']} kg",
        'typ': r['typ_ruchu'],
        'stacja': stacja_val,
        'akcja': r['komentarz'] or r['typ_ruchu'],
        'uzytkownik': r['autor_login']
    })

for d in data: print(d)
