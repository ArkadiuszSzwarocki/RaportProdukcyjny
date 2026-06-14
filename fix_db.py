import mysql.connector
import json
db = mysql.connector.connect(host='localhost', user='root', password='', database='raport_produkcyjny_v2')
cursor = db.cursor(dictionary=True)
cursor.execute("SELECT id, stan_przed, stan_po, zuzyte_worki FROM agro_workowanie_rozliczenie WHERE typ_zdarzenia='ZAMKNIECIE' AND zuzyte_worki != (stan_przed - stan_po)")
rows = cursor.fetchall()
if rows:
    for row in rows:
        cursor.execute("UPDATE agro_workowanie_rozliczenie SET zuzyte_worki = %s WHERE id = %s", (row['stan_przed'] - row['stan_po'], row['id']))
    db.commit()
print(json.dumps(rows))
