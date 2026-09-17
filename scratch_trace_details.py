import json
from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

pallet_no = 'SUR000001789020821513'
surowiec_id = 3191

print("=== SZCZEGÓŁY RUCHÓW DLA PALETY W DNIU 17.09.2026 ===")
cur.execute("""
    SELECT id, paleta_id, nr_palety, linia, typ_palety, akcja, 
           lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu
    FROM palety_historia
    WHERE (paleta_id = %s OR nr_palety = %s)
    ORDER BY data_ruchu ASC, id ASC
""", (surowiec_id, pallet_no))

for r in cur.fetchall():
    print(f"[{r['data_ruchu']}] ID: {r['id']} | AKCJA: {r['akcja']} | USER: {r['user_login']} | TRASA: {r['lokalizacja_zrodlowa']} -> {r['lokalizacja_docelowa']} | KOMENTARZ: {r['komentarz']} | LINIA: {r['linia']}")

print("\n=== MAGAZYN_RUCHY_UNIFIED ===")
cur.execute("""
    SELECT * FROM magazyn_ruchy_unified
    WHERE pallet_id = %s OR pallet_code = %s
    ORDER BY created_at ASC
""", (surowiec_id, pallet_no))
for r in cur.fetchall():
    print(f"[{r['created_at']}] TYP: {r['movement_type']} | USER: {r['user_login']} | QTY: {r['quantity']} {r['unit']} | TRASA: {r['source_location']} -> {r['target_location']} | NOTATKA: {r['notes']}")

print("\n=== CZY BYŁY JAKIEŚ ZLECENIA W MAGAZYN_DOSTAWY 17.09? ===")
cur.execute("""
    SELECT id, supplier, lokalizacja_z, lokalizacja_do, status, created_at, items
    FROM magazyn_dostawy
    WHERE items LIKE %s OR items LIKE %s
""", (f"%{pallet_no}%", f"%{surowiec_id}%"))
for d in cur.fetchall():
    print(f"Zlecenie ID: {d['id']} | Typ/Supplier: {d['supplier']} | Trasa: {d['lokalizacja_z']} -> {d['lokalizacja_do']} | Status: {d['status']} | Data: {d['created_at']}")
    try:
        raw_items = json.loads(d['items']) if isinstance(d['items'], str) else d['items']
        for it in raw_items:
            if pallet_no in str(it) or str(surowiec_id) in str(it):
                print("   Pozycja:", it)
    except Exception:
        pass

print("\n=== SPRAWDZENIE AKTYWNOŚCI USERA Magazynier i LuberBar W OKOLICY 08:30 - 08:35 (17.09.2026) ===")
cur.execute("""
    SELECT id, paleta_id, nr_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu
    FROM palety_historia
    WHERE data_ruchu BETWEEN '2026-09-17 08:25:00' AND '2026-09-17 08:40:00'
    ORDER BY data_ruchu ASC, id ASC
""")
for r in cur.fetchall():
    print(f"[{r['data_ruchu']}] USER: {r['user_login']} | PALETA: {r['nr_palety']} | AKCJA: {r['akcja']} | {r['lokalizacja_zrodlowa']} -> {r['lokalizacja_docelowa']} | {r['komentarz']}")

conn.close()
