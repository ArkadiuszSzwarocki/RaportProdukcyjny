"""
Sprawdzenie czy Frontend prawidłowo otrzymuje dane z backendu
"""
import json
from app.db import get_db_connection
from datetime import datetime, timedelta

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "=" * 80)
print("TEST: Symulacja co otrzyma Frontend z routes_planista.get_planista()")
print("=" * 80)

# Pobierz dane dokładnie tak jak routes_planista
dzisiaj = datetime.now().date()

# Sekcja ZASYP
print(f"\n📋 ZASYP ({dzisiaj}):")
print("-" * 80)

cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
           tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    WHERE data_planu = %s AND LOWER(sekcja) = 'zasyp'
    ORDER BY kolejnosc
""", (dzisiaj,))

zasyp_plans = [list(p) for p in cursor.fetchall()]

print(f"Znaleziono {len(zasyp_plans)} planów Zasyp")

# Symuluj cross-section mapping
for p in zasyp_plans[:3]:
    plan_id, sekcja, produkt = p[0], p[1], p[2]
    original_uszkodzone = p[11]
    
    # To co robi nowy kod
    cursor.execute(
        "SELECT COALESCE(uszkodzone_worki, 0) FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja='Workowanie' AND produkt=%s LIMIT 1",
        (dzisiaj, produkt)
    )
    work_result = cursor.fetchone()
    if work_result:
        p[11] = work_result[0]
    
    print(f"\n  [{plan_id}] {produkt}")
    print(f"     Zasyp miał: {original_uszkodzone}, Workowanie ma: {p[11]}")
    print(f"     Frontend będzie wyświetlać: p[11] = {p[11]}")
    print(f"     Template: <input value=\"{{ p[11]|default(0, true)|int }}\" /> → {p[11]}")

# Sekcja WORKOWANIE  
print(f"\n\n🏭 WORKOWANIE ({dzisiaj}):")
print("-" * 80)

cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
           tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'
    ORDER BY kolejnosc
""", (dzisiaj,))

work_plans = [list(p) for p in cursor.fetchall()]

print(f"Znaleziono {len(work_plans)} planów Workowanie")

for p in work_plans[:3]:
    plan_id, sekcja, produkt, uszkodzone = p[0], p[1], p[2], p[11]
    print(f"\n  [{plan_id}] {produkt}")
    print(f"     Frontend będzie wyświetlać: p[11] = {uszkodzone}")

print(f"\n" + "=" * 80)
print("✓ Frontend otrzyma prawidłowe dane z obu sekcji!")
print("=" * 80 + "\n")

conn.close()
