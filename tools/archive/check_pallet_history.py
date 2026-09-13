import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

cur.execute("""
    SELECT count(*) as cnt FROM palety_historia WHERE nr_palety IS NULL OR nr_palety = ''
""")
cnt = cur.fetchone()['cnt']
print("palety_historia rows without nr_palety:", cnt)

cur.execute("""
    UPDATE palety_historia ph
    JOIN magazyn_surowce ms ON ph.paleta_id = ms.id
    SET ph.nr_palety = ms.nr_palety
    WHERE (ph.nr_palety IS NULL OR ph.nr_palety = '') AND ms.nr_palety IS NOT NULL AND ms.nr_palety != ''
""")
updated_sur = cur.rowcount
print("Backfilled from magazyn_surowce:", updated_sur)

cur.execute("""
    UPDATE palety_historia ph
    JOIN magazyn_palety mp ON ph.paleta_id = mp.id
    SET ph.nr_palety = mp.nr_palety
    WHERE (ph.nr_palety IS NULL OR ph.nr_palety = '') AND mp.nr_palety IS NOT NULL AND mp.nr_palety != ''
""")
updated_pal = cur.rowcount
print("Backfilled from magazyn_palety:", updated_pal)

cur.execute("""
    UPDATE palety_historia ph
    JOIN magazyn_opakowania mo ON ph.paleta_id = mo.id
    SET ph.nr_palety = mo.nr_palety
    WHERE (ph.nr_palety IS NULL OR ph.nr_palety = '') AND mo.nr_palety IS NOT NULL AND mo.nr_palety != ''
""")
updated_opk = cur.rowcount
print("Backfilled from magazyn_opakowania:", updated_opk)

conn.commit()

# Check 9575 and 9606
cur.execute("SELECT id, paleta_id, nr_palety, akcja, komentarz FROM palety_historia WHERE id IN (9575, 9606)")
for r in cur.fetchall():
    print("  ", r)

conn.close()
