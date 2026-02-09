from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

dzisiaj = date.today()

# Symuluj co robi routes_planista - dla każdego planu Zasyp

# 1. Pobierz wszystkie plany Zasyp
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
           tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    ORDER BY kolejnosc
""", (dzisiaj,))

plany = [list(p) for p in cursor.fetchall()]

print("=" * 70)
print("SYMULACJA: Pobieranie uszkodzone_worki z Workowania")
print("=" * 70)

for p in plany[:5]:
    sekcja = (p[1] or '').lower()
    produkt = p[2]
    
    print(f"\n[Plan {p[0]}] {sekcja.upper():15} {produkt}")
    print(f"  Przed: p[11] = {p[11]}")
    
    # To co robi zmieniony kod - pobierz z Workowania
    if sekcja == 'zasyp':
        cursor.execute(
            "SELECT COALESCE(uszkodzone_worki, 0) FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja='Workowanie' AND produkt=%s LIMIT 1",
            (dzisiaj, produkt)
        )
        work_result = cursor.fetchone()
        if work_result:
            p[11] = work_result[0]
            print(f"  Znalazł Workowanie: p[11] = {p[11]}")
        else:
            print(f"  Brak Workowania - p[11] = {p[11]}")
    else:
        print(f"  (to jest {sekcja}, nie Zasyp)")

print("\n" + "=" * 70)
print("✓ Teraz kolumna będzie pokazywać dane z Workowania!")
print("=" * 70)

conn.close()
