import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection

sys.stdout.reconfigure(encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

print("--- DESCRIBE pracownicy ---")
cursor.execute("DESCRIBE pracownicy")
for row in cursor.fetchall():
    print(row)

print("--- SELECT * FROM pracownicy WHERE id = 40 ---")
cursor.execute("SELECT * FROM pracownicy WHERE id = 40")
row = cursor.fetchone()
print(row)

conn.close()
