import sys
import os

sys.path.append(os.path.abspath('a:\\GitHub\\RaportProdukcyjny'))
from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute('SELECT nazwa FROM magazyn_dozwolone_lokalizacje')
valid_prefixes = [row[0] for row in cur.fetchall()]

def clean_table(table_name):
    cur.execute(f"SELECT id, lokalizacja FROM {table_name} WHERE lokalizacja IS NOT NULL AND lokalizacja != ''")
    rows = cur.fetchall()
    updated = 0
    for row in rows:
        loc = row[1].upper()
        if not any(loc.startswith(vp) for vp in valid_prefixes):
            cur.execute(f"UPDATE {table_name} SET lokalizacja = NULL WHERE id = %s", (row[0],))
            updated += 1
    return updated

u1 = clean_table('magazyn_surowce')
u2 = clean_table('magazyn_agro_surowce')
conn.commit()
conn.close()

print(f'Cleaned up PSD: {u1}, AGRO: {u2}')
