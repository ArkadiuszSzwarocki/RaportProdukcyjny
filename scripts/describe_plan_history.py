from app.config import DB_CONFIG
import mysql.connector

try:
    cnx = mysql.connector.connect(**DB_CONFIG)
    cur = cnx.cursor()
    cur.execute("DESCRIBE plan_history")
    rows = cur.fetchall()
    for r in rows:
        print(r)
    cur.close()
    cnx.close()
except Exception as e:
    print('ERROR:', e)
