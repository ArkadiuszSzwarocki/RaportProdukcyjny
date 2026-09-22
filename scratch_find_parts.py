from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

# User typed: PSD00000178721629555 (20 chars)
# Let's search by parts: '1787216', '721629', '162955'
parts = ['1787216', '721629', '162955', '7216295', '178721', '629555']

for p in parts:
    print(f"\n--- Checking part: {p} ---")
    cur.execute("SELECT id, nr_palety, plan_id, status, data_dodania, waga FROM palety_workowanie WHERE nr_palety LIKE %s", (f"%{p}%",))
    r1 = cur.fetchall()
    if r1:
        print(f"  palety_workowanie: {r1}")
        
    cur.execute("SELECT id, nr_palety, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, created_at, data_ruchu FROM palety_historia WHERE nr_palety LIKE %s", (f"%{p}%",))
    r2 = cur.fetchall()
    if r2:
        print(f"  palety_historia: {r2}")
        
    cur.execute("SELECT id, nr_palety, produkt, status, lokalizacja, data_produkcji FROM magazyn_palety WHERE nr_palety LIKE %s", (f"%{p}%",))
    r3 = cur.fetchall()
    if r3:
        print(f"  magazyn_palety: {r3}")
        
    cur.execute("SELECT id, typ_dokumentu, nr_dokumentu, supplier, status, items FROM magazyn_dostawy WHERE items LIKE %s", (f"%{p}%",))
    r4 = cur.fetchall()
    if r4:
        print(f"  magazyn_dostawy: {r4}")

conn.close()
