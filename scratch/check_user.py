import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection

sys.stdout.reconfigure(encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

print("--- SELECT * FROM uzytkownicy WHERE login = 'GrysDawi' ---")
cursor.execute("SELECT id, login, rola, grupa, pracownik_id FROM uzytkownicy WHERE login = 'GrysDawi'")
row = cursor.fetchone()
print(row)

print("--- SELECT * FROM uzytkownicy ---")
cursor.execute("SELECT id, login, rola, grupa, pracownik_id FROM uzytkownicy")
for row in cursor.fetchall():
    print(row)

conn.close()
