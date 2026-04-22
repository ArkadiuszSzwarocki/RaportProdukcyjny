from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute('SHOW CREATE TABLE zasyp_etapy;')
res = cursor.fetchone()
print(res['Create Table'])
conn.close()
