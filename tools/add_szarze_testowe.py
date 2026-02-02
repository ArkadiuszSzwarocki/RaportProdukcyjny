from db import get_db_connection
from datetime import datetime, time

conn = get_db_connection()
cursor = conn.cursor()

# Pobierz plany Zasyp na dzisiaj
cursor.execute("""
    SELECT id, produkt, tonaz 
    FROM plan_produkcji 
    WHERE data_planu = '2026-02-02' AND sekcja = 'Zasyp'
    ORDER BY id
""")

plans = cursor.fetchall()
print("=" * 100)
print("DODAWANIE SZARŻ NA DZISIAJ")
print("=" * 100)

# Dla każdego planu dodaj kilka szarż
szarze_data = [
    # GOLDMILK LEN (5000) - plan_id 396
    (396, 1500, "08:30:00"),
    (396, 1800, "09:15:00"),
    (396, 1700, "10:00:00"),
    
    # MULTI MILK PRO (6000) - plan_id 393
    (393, 2000, "08:00:00"),
    (393, 2000, "09:00:00"),
    (393, 2000, "10:00:00"),
    
    # MULTI MILK PRO (2000) - plan_id 397
    (397, 1050, "10:30:00"),
    (397, 1025, "11:15:00"),
    
    # PEŁNOMLECZNY (2000) - plan_id 398
    (398, 1000, "09:30:00"),
    (398, 1000, "10:30:00"),
    
    # AGROS 3 LEN (3000) - plan_id 399
    (399, 1500, "11:00:00"),
    (399, 1500, "12:00:00"),
    
    # AGROS MILK EKO (3000) - plan_id 400
    (400, 1500, "12:30:00"),
    (400, 1500, "13:30:00"),
]

# Insert szarży
for plan_id, waga, godzina in szarze_data:
    cursor.execute("""
        INSERT INTO szarze (plan_id, waga, data_dodania, godzina, status)
        VALUES (%s, %s, '2026-02-02 12:00:00', %s, 'zarejestowana')
    """, (plan_id, waga, godzina))
    
    # Odczytaj plan details
    cursor.execute("SELECT produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
    prod = cursor.fetchone()
    produkt = prod[0] if prod else "NIEZNANY"
    
    print(f"✅ plan_id={plan_id:3} ({produkt:20}) + szarża {waga} kg o {godzina}")

conn.commit()
conn.close()

print("\n" + "=" * 100)
print("PODSUMOWANIE")
print("=" * 100)

# Teraz sprawdź co się dodało
conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT p.id, p.produkt, p.tonaz, SUM(sz.waga) as suma_szarz, COUNT(sz.id) as ilosc_szarz
    FROM plan_produkcji p
    LEFT JOIN szarze sz ON p.id = sz.plan_id
    WHERE p.data_planu = '2026-02-02' AND p.sekcja = 'Zasyp'
    GROUP BY p.id, p.produkt, p.tonaz
    ORDER BY p.id
""")

print("\nPlan | Produkt                 | Plan (tonaz) | Wykonanie (szarże) | Ilość szarż")
print("-" * 90)
for row in cursor.fetchall():
    plan_id, produkt, plan_waga, suma_szarz, ilosc = row
    suma_szarz = suma_szarz or 0
    ilosc = ilosc or 0
    print(f"{plan_id:3} | {produkt:20} | {plan_waga:12.0f} | {suma_szarz:18.0f} | {ilosc:11}")

cursor.execute("""
    SELECT SUM(sz.waga) as total_szarze
    FROM szarze sz
    JOIN plan_produkcji p ON sz.plan_id = p.id
    WHERE p.data_planu = '2026-02-02' AND p.sekcja = 'Zasyp'
""")

total = cursor.fetchone()[0] or 0
print("-" * 90)
print(f"RAZEM WYKONANIE SZARŻ: {total:.0f} kg")

conn.close()
