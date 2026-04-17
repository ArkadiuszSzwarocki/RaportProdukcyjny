"""Diagnostyka: polmlek czerwony - bufor vs zasyp vs workowanie"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import mysql.connector

conn = mysql.connector.connect(
    host='filipinka.myqnapcloud.com',
    port=3307,
    database='biblioteka',
    user='biblioteka',
    password='Filipinka2025',
    charset='utf8mb4',
    buffered=True
)
cur = conn.cursor(dictionary=True)

print("=" * 100)
print("1. BUFOR — wpisy zawierające 'polmlek'")
print("=" * 100)
cur.execute("""
    SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.kolejka, b.status,
           b.tonaz_rzeczywisty, b.spakowano, b.created_at
    FROM bufor b
    WHERE LOWER(b.produkt) LIKE '%polmlek%'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 30
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 100)
print("2. POWIĄZANIA: bufor → Zasyp → Workowanie (polmlek)")
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
    WHERE LOWER(b.produkt) LIKE '%polmlek%'
    ORDER BY b.data_planu DESC, b.kolejka
    LIMIT 30
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 100)
print("3. Plany 'polmlek' z ostatnich 5 dni (plan_produkcji)")
print("=" * 100)
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty,
           kolejnosc, zasyp_id, is_deleted
    FROM plan_produkcji
    WHERE LOWER(produkt) LIKE '%polmlek%'
      AND data_planu >= DATE_SUB(CURDATE(), INTERVAL 5 DAY)
    ORDER BY data_planu DESC, sekcja, kolejnosc
""")
for r in cur.fetchall():
    print(r)

print()
print("=" * 100)
print("4. Unikalne produkty 'polmlek' w buforze i planie")
print("=" * 100)
cur.execute("SELECT DISTINCT produkt FROM bufor WHERE LOWER(produkt) LIKE '%polmlek%'")
print("Bufor:", [r['produkt'] for r in cur.fetchall()])
cur.execute("SELECT DISTINCT produkt FROM plan_produkcji WHERE LOWER(produkt) LIKE '%polmlek%'")
print("Plan:", [r['produkt'] for r in cur.fetchall()])

print()
print("=" * 100)
print("5. Palety workowanie powiązane z polmlek (ostatnie 5 dni)")
print("=" * 100)
cur.execute("""
    SELECT pw.id, pw.plan_id, pw.waga, pw.data_dodania, pw.status
    FROM palety_workowanie pw
    INNER JOIN plan_produkcji p ON p.id = pw.plan_id
    WHERE LOWER(p.produkt) LIKE '%polmlek%'
      AND p.data_planu >= DATE_SUB(CURDATE(), INTERVAL 5 DAY)
    ORDER BY pw.data_dodania DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print(r)

cur.close()
conn.close()
print("\nDone.")
