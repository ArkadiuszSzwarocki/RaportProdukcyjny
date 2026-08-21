from app.db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT id FROM slownik_etykiety_agro WHERE nazwa='Biała z paskiem czerwonym'")
res = cursor.fetchone()
if not res:
    cursor.execute("INSERT INTO slownik_etykiety_agro (nazwa) VALUES ('Biała z paskiem czerwonym')")
    conn.commit()
    print('Inserted label.')
else:
    print('Label already exists.')
conn.close()
