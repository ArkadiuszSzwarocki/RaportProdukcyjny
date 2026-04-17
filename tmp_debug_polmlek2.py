"""Diagnostyka: polmlek czerwony - bufor vs zasyp vs workowanie
Łączy się przez filipinka.myqnapcloud.com:3307 do bazy 'biblioteka'
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Override env before importing app config
os.environ['DB_HOST'] = 'filipinka.myqnapcloud.com'
os.environ['DB_NAME'] = 'biblioteka'

from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

print("=" * 100)
print("1. BUFOR — wpisy zawierające 'polmlek' (aktywne i ostatnie)")
print("=" * 100)
cur.execute("""
    SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.kolejka, b.status,
           b.tonaz_rzeczywisty, b.spakowano, b.created_at
    FROM bufor b
    WHERE LOWER(b.produkt) LIKE '%polmlek%czerw%'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 20
""")
rows = cur.fetchall()
if not rows:
    print("  (brak wyników - szukam szerzej...)")
    cur.execute("SELECT DISTINCT produkt FROM bufor WHERE LOWER(produkt) LIKE '%polmlek%' ORDER BY produkt")
    for r in cur.fetchall():
        print(f"  produkt w buforze: {r['produkt']}")
else:
    for r in rows:
        print(r)

print()
print("=" * 100)
print("2. POWIĄZANIA: bufor → Zasyp → Workowanie")
print("=" * 100)
cur.execute("""
    SELECT b.id AS bufor_id, b.zasyp_id, b.data_planu, b.produkt, b.kolejka,
           b.status AS bufor_status, b.tonaz_rzeczywisty AS buf_tonaz, b.spakowano,
           z.id AS zasyp_plan_id, z.status AS zasyp_status, z.tonaz AS z_tonaz, z.tonaz_rzeczywisty AS z_real,
           w.id AS work_id, w.status AS work_status, w.tonaz AS w_tonaz,
           w.tonaz_rzeczywisty AS w_real, w.zasyp_id AS w_zasyp_fk
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id AND LOWER(z.sekcja) = 'zasyp'
    LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id AND LOWER(w.sekcja) = 'workowanie'
    WHERE LOWER(b.produkt) LIKE '%polmlek%czerw%'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 20
""")
rows = cur.fetchall()
if not rows:
    print("  (brak wyników)")
    # Szersza wersja - szukaj wszystkich polmlek
    cur.execute("""
        SELECT b.id AS bufor_id, b.zasyp_id, b.data_planu, b.produkt, b.kolejka,
               b.status AS bufor_status, b.tonaz_rzeczywisty AS buf_tonaz, b.spakowano,
               z.status AS zasyp_status,
               w.id AS work_id, w.status AS work_status, w.zasyp_id AS w_zasyp_fk
        FROM bufor b
        LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id AND LOWER(z.sekcja) = 'zasyp'
        LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id AND LOWER(w.sekcja) = 'workowanie'
        WHERE LOWER(b.produkt) LIKE '%polmlek%'
        ORDER BY b.data_planu DESC, b.kolejka
        LIMIT 20
    """)
    for r in cur.fetchall():
        print(r)
else:
    for r in rows:
        print(r)

print()
print("=" * 100)
print("3. Plany 'polmlek czerw' z ostatnich 5 dni (plan_produkcji)")
print("=" * 100)
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty,
           kolejnosc, zasyp_id, is_deleted
    FROM plan_produkcji
    WHERE LOWER(produkt) LIKE '%polmlek%czerw%'
      AND data_planu >= DATE_SUB(CURDATE(), INTERVAL 5 DAY)
    ORDER BY data_planu DESC, sekcja, kolejnosc
""")
rows = cur.fetchall()
if not rows:
    print("  (brak — szukam szerzej po samym 'polmlek')")
    cur.execute("""
        SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty,
               kolejnosc, zasyp_id, is_deleted
        FROM plan_produkcji
        WHERE LOWER(produkt) LIKE '%polmlek%'
          AND data_planu >= DATE_SUB(CURDATE(), INTERVAL 5 DAY)
        ORDER BY data_planu DESC, sekcja, kolejnosc
    """)
    rows = cur.fetchall()
for r in rows:
    print(r)

print()
print("=" * 100)
print("4. Wszystkie unikalne produkty 'polmlek' w buforze i planie")
print("=" * 100)
cur.execute("SELECT DISTINCT produkt FROM bufor WHERE LOWER(produkt) LIKE '%polmlek%'")
print("Bufor:", [r['produkt'] for r in cur.fetchall()])
cur.execute("SELECT DISTINCT produkt FROM plan_produkcji WHERE LOWER(produkt) LIKE '%polmlek%'")
print("Plan:", [r['produkt'] for r in cur.fetchall()])

cur.close()
conn.close()
print("\nDone.")
