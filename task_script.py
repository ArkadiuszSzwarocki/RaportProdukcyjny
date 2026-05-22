import sys
import os
import pymysql
from datetime import date

sys.path.append(os.getcwd())

try:
    from app.config import DB_CONFIG
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

config = DB_CONFIG.copy()
config['database'] = 'biblioteka_testowa'

try:
    conn = pymysql.connect(**config)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
except Exception as e:
    print(f"Error connecting to DB: {e}")
    sys.exit(1)

print("--- active_db.txt ---")
try:
    with open('active_db.txt', 'r', encoding='utf-8') as f:
        print(f.read().strip())
except FileNotFoundError:
    print("active_db.txt not found")
print("")

today = date.today().isoformat()

print("--- Today's Plan Summary (sekcja, status) ---")
query3 = "SELECT sekcja, status, COUNT(*) as count FROM plan_produkcji_agro WHERE DATE(data_planu) = %s GROUP BY sekcja, status"
cursor.execute(query3, (today,))
results3 = cursor.fetchall()
for row in results3:
    print(f"Sekcja: {str(row['sekcja']):<15} | Status: {str(row['status']):<15} | Count: {row['count']}")
print("")

print("--- Latest 15 entries in plan_produkcji_agro ---")
query4 = "SELECT id, data_planu, sekcja, produkt, status, is_deleted, kolejnosc FROM plan_produkcji_agro ORDER BY id DESC LIMIT 15"
cursor.execute(query4)
results4 = cursor.fetchall()
print(f"{'ID':<6} | {'Data':<11} | {'Sekcja':<15} | {'Produkt':<20} | {'Status':<12} | {'Del':<3} | {'Kol':<3}")
print("-" * 85)
for row in results4:
    print(f"{row['id']:<6} | {str(row['data_planu']):<11} | {str(row['sekcja']):<15} | {str(row['produkt'])[:20]:<20} | {str(row['status']):<12} | {row['is_deleted']:<3} | {row['kolejnosc']:<3}")
print("")

print("--- Dashboard Guard Check: Workowanie ---")
query5 = """
    SELECT COUNT(*) as count 
    FROM plan_produkcji_agro 
    WHERE DATE(data_planu) = %s 
      AND LOWER(sekcja) = 'workowanie' 
      AND status != 'nieoplacone' 
      AND is_deleted = 0
"""
cursor.execute(query5, (today,))
result5 = cursor.fetchone()
print(f"Count for Workowanie (CURDATE, !nieoplacone, !deleted): {result5['count']}")

cursor.close()
conn.close()
