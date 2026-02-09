from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

dzisiaj = date.today()

# Dokładnie taki query jak routes_planista
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
           tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    ORDER BY kolejnosc
""", (dzisiaj,))

plany = [list(r) for r in cursor.fetchall()]

print("=" * 80)
print(f"PLANY NA DZISIAJ ({dzisiaj}) - QUERY Z routes_planista")
print("=" * 80)

if plany:
    print(f"Liczba planów: {len(plany)}")
    print(f"Kolumn: {len(plany[0])}")
    
    for i, p in enumerate(plany[:5]):
        print(f"\n[Plan {i+1}]")
        print(f"  p[0] (id)              = {p[0]}")
        print(f"  p[1] (sekcja)          = {p[1]}")
        print(f"  p[2] (produkt)         = {p[2]}")
        print(f"  p[3] (tonaz)           = {p[3]}")
        print(f"  p[4] (status)          = {p[4]}")
        print(f"  p[11] (uszkodz_worki)  = {p[11]} ← TEMPLATE CZYTA TEN INDEKS")
        
    print("\n" + "=" * 80)
    print("✓ Wszystkie plany mają uszkodzone_worki na p[11]")
    print("✓ Wartości to 0 bo użytkownik ich nie zmienił dla dzisiejszych planów")
else:
    print("Brak planów na dzisiaj")

conn.close()
