from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

pallet_no = "PSD00000178721629555"

tables = [
    "palety_workowanie", "magazyn_palety", "magazyn_palety_agro", "palety_agro", 
    "palety_historia", "magazyn_dostawy", "backup_magazyn_palety", "backup_magazyn_palety_agro",
    "print_jobs", "magazyn_kompletacja", "magazyn_zaladunki", "magazyn_archiwum"
]

print(f"Searching for {pallet_no} in key tables...")

for t in tables:
    try:
        cur.execute(f"SHOW COLUMNS FROM {t}")
        cols = [c['Field'] for c in cur.fetchall()]
        for col in cols:
            cur.execute(f"SELECT * FROM {t} WHERE `{col}` = %s OR `{col}` LIKE %s", (pallet_no, f"%{pallet_no}%"))
            rows = cur.fetchall()
            if rows:
                print(f"MATCH IN {t}.{col}: {rows}")
    except Exception as e:
        print(f"Error checking {t}: {e}")

# Also let's search if digits '178721629555' match with a different prefix like 'AGR' or 'SUR' or 'PAL' or 'PRD' or without prefix
digits = "178721629555"
print(f"\nSearching for digits {digits} across tables...")
for t in tables:
    try:
        cur.execute(f"SHOW COLUMNS FROM {t}")
        cols = [c['Field'] for c in cur.fetchall()]
        for col in cols:
            cur.execute(f"SELECT * FROM {t} WHERE `{col}` LIKE %s", (f"%{digits}%",))
            rows = cur.fetchall()
            if rows:
                print(f"DIGIT MATCH IN {t}.{col}: {rows}")
    except Exception as e:
        pass

conn.close()
