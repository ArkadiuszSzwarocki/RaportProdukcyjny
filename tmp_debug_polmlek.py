"""Diagnostyka: polmlek czerwony - bufor vs zasyp vs workowanie"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

print("=" * 90)
print("1. BUFOR — wpisy zawierające 'polmlek' (aktywne i ostatnie)")
print("=" * 90)
cur.execute("""
    SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.kolejka, b.status,
           b.tonaz_rzeczywisty, b.spakowano, b.created_at
    FROM bufor b
    WHERE LOWER(b.produkt) LIKE '%polmlek%czerw%'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 20
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 90)
print("2. ZASYP — plan_produkcji sekcja=Zasyp dla polmlek czerwony")
print("=" * 90)
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty,
           real_start, real_stop, kolejnosc, zasyp_id, is_deleted
    FROM plan_produkcji
    WHERE LOWER(produkt) LIKE '%polmlek%czerw%' AND LOWER(sekcja) = 'zasyp'
    ORDER BY data_planu DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 90)
print("3. WORKOWANIE — plan_produkcji sekcja=Workowanie dla polmlek czerwony")
print("=" * 90)
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty,
           real_start, real_stop, kolejnosc, zasyp_id, is_deleted
    FROM plan_produkcji
    WHERE LOWER(produkt) LIKE '%polmlek%czerw%' AND LOWER(sekcja) = 'workowanie'
    ORDER BY data_planu DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 90)
print("4. POWIĄZANIA: bufor.zasyp_id -> plan(Zasyp) -> plan(Workowanie via zasyp_id)")
print("=" * 90)
cur.execute("""
    SELECT b.id AS bufor_id, b.zasyp_id, b.data_planu, b.produkt, b.kolejka, b.status AS bufor_status,
           b.tonaz_rzeczywisty AS buf_tonaz, b.spakowano AS buf_spakowano,
           z.id AS zasyp_plan_id, z.status AS zasyp_status, z.tonaz AS z_tonaz, z.tonaz_rzeczywisty AS z_real,
           w.id AS work_id, w.status AS work_status, w.tonaz AS w_tonaz, w.tonaz_rzeczywisty AS w_real, w.zasyp_id AS w_zasyp_id
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id AND LOWER(z.sekcja) = 'zasyp'
    LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id AND LOWER(w.sekcja) = 'workowanie'
    WHERE LOWER(b.produkt) LIKE '%polmlek%czerw%'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 20
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 90)
print("5. Wszystkie wpisy z 'polmlek czerw' z dzisiaj i wczoraj (plan_produkcji)")
print("=" * 90)
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty,
           real_start, real_stop, kolejnosc, zasyp_id, is_deleted
    FROM plan_produkcji
    WHERE LOWER(produkt) LIKE '%polmlek%czerw%'
      AND data_planu >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
    ORDER BY data_planu DESC, sekcja, kolejnosc
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 90)
print("6. Czy istnieje kolumna 'linia' w buforze?")
print("=" * 90)
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='bufor' AND COLUMN_NAME='linia'")
col = cur.fetchone()
print(f"Kolumna 'linia' w bufor: {'TAK' if col else 'NIE'}")

if col:
    cur.execute("""
        SELECT id, zasyp_id, data_planu, produkt, kolejka, status, linia
        FROM bufor WHERE LOWER(produkt) LIKE '%polmlek%czerw%' ORDER BY data_planu DESC LIMIT 10
    """)
    for r in cur.fetchall():
        print(r)

cur.close()
conn.close()
print("\nDone.")
