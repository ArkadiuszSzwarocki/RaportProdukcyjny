import sys
import os
from dotenv import load_dotenv

load_dotenv()

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Find used locations starting with R0301
cursor.execute("SELECT lokalizacja FROM magazyn_agro_surowce WHERE lokalizacja LIKE 'R0301%'")
used_locs = {r['lokalizacja'] for r in cursor.fetchall()}

# Find pallets with NO location
cursor.execute("SELECT id, nazwa, stan_magazynowy, lokalizacja FROM magazyn_agro_surowce WHERE stan_magazynowy > 0 AND (lokalizacja IS NULL OR lokalizacja = '') ORDER BY id ASC")
pallets = cursor.fetchall()
print(f'Found {len(pallets)} pallets without location.')

if pallets:
    current_index = 1
    for p in pallets:
        # Find next available loc
        loc = None
        while True:
            num = str(current_index).zfill(2)
            candidate = f'R0301{num}'
            if candidate not in used_locs:
                loc = candidate
                used_locs.add(loc)
                break
            current_index += 1
            
        cursor.execute("UPDATE magazyn_agro_surowce SET lokalizacja = %s WHERE id = %s", (loc, p['id']))
        print(f"Updated {p['nazwa']} (ID: {p['id']}) to {loc}")
    conn.commit()
conn.close()
