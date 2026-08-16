import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor(dictionary=True)
cursor.execute("DESCRIBE plan_produkcji")
for row in cursor.fetchall():
    print(row['Field'], row['Type'])
