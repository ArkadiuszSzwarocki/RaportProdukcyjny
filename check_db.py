import mysql.connector
c = mysql.connector.connect(host='localhost', user='root', password='', database='raport_produkcyjny')
cur=c.cursor()
cur.execute("SELECT id, produkt, opakowanie_id, etykieta_id FROM plan_produkcji_agro WHERE data_planu=CURDATE() AND status='zaplanowane'")
print(cur.fetchall())
