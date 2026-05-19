import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection

sys.stdout.reconfigure(encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

print("--- DESCRIBE plan_produkcji_agro ---")
cursor.execute("DESCRIBE plan_produkcji_agro")
for col in cursor.fetchall():
    print(f"{col['Field']}: {col['Type']} (Null: {col['Null']})")

print("\n--- SAMPLE FROM magazyn_opakowania ---")
cursor.execute("SELECT id, nazwa, stan_magazynowy, lokalizacja FROM magazyn_opakowania LIMIT 10")
for row in cursor.fetchall():
    print(row)

conn.close()
