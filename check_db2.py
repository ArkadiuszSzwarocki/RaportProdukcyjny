import mysql.connector
c = mysql.connector.connect(host='127.0.0.1', port=3307, user='biblioteka', password='', database='biblioteka')
cur=c.cursor(dictionary=True)
cur.execute("SELECT id, produkt, opakowanie_id, etykieta_id FROM plan_produkcji_agro WHERE status='zaplanowane'")
print(cur.fetchall())
