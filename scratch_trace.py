import json
from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

pallet_no = 'SUR000001789020821513'
surowiec_id = 3191

print(f"SZUKAM TRACEABILITY DLA PALETY: {pallet_no} (surowiec_id={surowiec_id})\n")

print("=== 1. MAGAZYN_ARCHIWUM ===")
cur.execute("SELECT * FROM magazyn_archiwum WHERE nr_palety = %s OR original_id = %s", (pallet_no, surowiec_id))
for r in cur.fetchall():
    print(r)

print("\n=== 2. MAGAZYN_SUROWCE ===")
cur.execute("SELECT * FROM magazyn_surowce WHERE id = %s OR nr_palety = %s", (surowiec_id, pallet_no))
for r in cur.fetchall():
    print(r)

print("\n=== 3. MAGAZYN_RUCH (po surowiec_id={surowiec_id}) ===")
cur.execute("SELECT * FROM magazyn_ruch WHERE surowiec_id = %s ORDER BY autor_data ASC, id ASC", (surowiec_id,))
rows_ruch = cur.fetchall()
print(f"Liczba wpisów w magazyn_ruch: {len(rows_ruch)}")
for r in rows_ruch:
    print(r)

print("\n=== 4. PALETY_HISTORIA (po paleta_id={surowiec_id} lub nr_palety) ===")
try:
    cur.execute("SELECT * FROM palety_historia WHERE paleta_id = %s OR nr_palety = %s ORDER BY data_ruchu ASC", (surowiec_id, pallet_no))
    rows_hist = cur.fetchall()
    print(f"Liczba wpisów w palety_historia: {len(rows_hist)}")
    for r in rows_hist:
        print(r)
except Exception as e:
    print("palety_historia error:", e)

print("\n=== 5. MAGAZYN_RUCHY_UNIFIED ===")
try:
    cur.execute("SELECT * FROM magazyn_ruchy_unified WHERE pallet_id = %s OR pallet_code = %s ORDER BY created_at ASC", (surowiec_id, pallet_no))
    rows_unif = cur.fetchall()
    print(f"Liczba wpisów w magazyn_ruchy_unified: {len(rows_unif)}")
    for r in rows_unif:
        print(r)
except Exception as e:
    print("magazyn_ruchy_unified error:", e)

print("\n=== 6. MAGAZYN_DOSTAWY (przeszukiwanie JSON) ===")
cur.execute("SELECT id, supplier, lokalizacja_z, lokalizacja_do, status, items, created_at, updated_at FROM magazyn_dostawy ORDER BY id DESC LIMIT 200")
for d in cur.fetchall():
    raw = str(d.get('items') or '')
    if pallet_no in raw or str(surowiec_id) in raw:
        print("Dostawa/Zlecenie ID:", d['id'], "Supplier/Ref:", d['supplier'], "Status:", d['status'], "Created:", d['created_at'], "Updated:", d['updated_at'])
        try:
            items = json.loads(d['items']) if isinstance(d['items'], str) else d['items']
            for it in items:
                if pallet_no in str(it) or str(surowiec_id) in str(it):
                    print("  Pozycja:", it)
        except Exception:
            pass

print("\n=== 7. SZARZE / PRODUKCJA (zużycie w szarżach/planach) ===")
try:
    cur.execute("""
        SELECT s.*, p.produkt, p.data_planu, p.sekcja
        FROM szarze s
        JOIN plan_produkcji p ON s.plan_id = p.id
        WHERE s.data_dodania >= '2026-09-17 00:00:00'
        ORDER BY s.data_dodania ASC
    """)
    szarze_today = cur.fetchall()
    print(f"Szarze w dniu 17.09: {len(szarze_today)}")
except Exception as e:
    print("szarze error:", e)

conn.close()
