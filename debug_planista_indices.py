from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Dokładnie ten sam query co w routes_planista.py
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
           tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    ORDER BY kolejnosc
""", (date.today(),))

plany = [list(p) for p in cursor.fetchall()]

print("=" * 70)
print(f"Query z routes_planista - PRZED append: {len(plany[0])} kolumn")
print("=" * 70)

if plany:
    p = plany[0]
    print(f"\nPierwszy plan (ID={p[0]}):")
    for i in range(min(13, len(p))):
        print(f"  p[{i:2}] = {p[i]}")

# Symuluje co robi routes_planista.py linia 85
print("\n" + "=" * 70)
print("SYMULACJA: p.append(czas_trwania_min) na linii 85")
print("=" * 70)

if plany:
    p = plany[0]
    czas_trwania_min = 60  # przykład
    p.append(czas_trwania_min)
    
    print(f"\nPo append: {len(p)} kolumn")
    print(f"\nPierwszy plan (ID={p[0]}) PO APPEND:")
    for i in range(len(p)):
        print(f"  p[{i:2}] = {p[i]}")
    
    print(f"\nTEMPLATE CZYTA: p[11] = {p[11]} (ale to powinno być uszkodzone_worki!)")
    print(f"RZECZYWISCIE: p[11] = CZAS, uszkodzone_worki jest teraz na p[11] PRZED append = oryginalny p[11]")

conn.close()
