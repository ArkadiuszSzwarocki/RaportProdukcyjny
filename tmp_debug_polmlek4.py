"""Sprawdzenie pełnej kolejki bufora na dziś i logiki blokowania"""
import mysql.connector

conn = mysql.connector.connect(
    host='filipinka.myqnapcloud.com', port=3307,
    database='biblioteka', user='biblioteka', password='Filipinka2025',
    charset='utf8mb4', buffered=True
)
cur = conn.cursor(dictionary=True)

print("=" * 110)
print("CAŁA KOLEJKA BUFORA NA DZIŚ (2026-04-17) — wszystkie produkty")
print("=" * 110)
cur.execute("""
    SELECT b.id AS bufor_id, b.zasyp_id, b.produkt, b.kolejka, b.status AS bufor_status,
           b.tonaz_rzeczywisty AS buf_tonaz, b.spakowano,
           (b.tonaz_rzeczywisty - b.spakowano) AS reszta,
           z.status AS zasyp_status,
           w.id AS work_id, w.status AS work_status, w.tonaz AS w_tonaz, w.tonaz_rzeczywisty AS w_real
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id AND LOWER(z.sekcja) = 'zasyp'
    LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id AND LOWER(w.sekcja) = 'workowanie'
    WHERE b.data_planu = '2026-04-17'
    ORDER BY b.kolejka ASC
""")
for r in cur.fetchall():
    marker = " <<<< POLMLEK CZERWONY" if 'CZERWON' in (r['produkt'] or '').upper() else ""
    print(f"  kol={r['kolejka']:2d} | {r['bufor_status']:12s} | {r['produkt']:30s} | buf_tonaz={r['buf_tonaz']:8.0f} spak={r['spakowano']:8.0f} reszta={r['reszta']:8.0f} | zasyp={r['zasyp_status']} | work_id={r['work_id']} work_status={r['work_status']} w_real={r['w_real']}{marker}")

print()
print("=" * 110)
print("Kolumna 'linia' w buforze?")
print("=" * 110)
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='bufor' AND COLUMN_NAME='linia'")
col = cur.fetchone()
print(f"  Kolumna 'linia': {'TAK' if col else 'NIE'}")

if col:
    cur.execute("SELECT id, produkt, kolejka, status, linia FROM bufor WHERE data_planu='2026-04-17' ORDER BY kolejka")
    for r in cur.fetchall():
        print(f"  id={r['id']} kol={r['kolejka']} linia={r['linia']} status={r['status']} produkt={r['produkt']}")

cur.close()
conn.close()
print("\nDone.")
