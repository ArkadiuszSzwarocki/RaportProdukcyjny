import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection

sys.stdout.reconfigure(encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

try:
    print("--- DESCRIBE zasyp_etapy ---")
    cursor.execute("DESCRIBE zasyp_etapy")
    for col in cursor.fetchall():
        print(f"{col['Field']}: {col['Type']} (Null: {col['Null']})")
except Exception as e:
    print("Failed describing zasyp_etapy:", e)

try:
    print("\n--- DESCRIBE zasyp_etapy_parametry ---")
    cursor.execute("DESCRIBE zasyp_etapy_parametry")
    for col in cursor.fetchall():
        print(f"{col['Field']}: {col['Type']} (Null: {col['Null']})")
except Exception as e:
    print("Failed describing zasyp_etapy_parametry:", e)

try:
    print("\n--- RECENT ROWS FROM zasyp_etapy ---")
    cursor.execute("SELECT * FROM zasyp_etapy ORDER BY id DESC LIMIT 10")
    for row in cursor.fetchall():
        print(row)
except Exception as e:
    print("Failed querying zasyp_etapy:", e)

try:
    print("\n--- ACTIVE PLANS FOR AGRO ---")
    cursor.execute("SELECT id, status, produkt FROM plan_produkcji_agro WHERE status IN ('w toku', 'zaplanowane') LIMIT 10")
    for row in cursor.fetchall():
        print(row)
except Exception as e:
    print("Failed querying plan_produkcji_agro:", e)

conn.close()
