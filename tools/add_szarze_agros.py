from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Dodaj szarże dla AGROS
szarze_data = [
    (399, 1500, "11:00:00"),
    (399, 1500, "12:00:00"),
    (400, 1500, "12:30:00"),
    (400, 1500, "13:30:00"),
]

for plan_id, waga, godzina in szarze_data:
    cursor.execute("""
        INSERT INTO szarze (plan_id, waga, data_dodania, godzina, status)
        VALUES (%s, %s, '2026-02-02 12:00:00', %s, 'zarejestowana')
    """, (plan_id, waga, godzina))
    print(f"✅ Dodana szarża: plan_id={plan_id}, waga={waga} kg, godzina={godzina}")

conn.commit()

# Pokaż podsumowanie
cursor.execute("""
    SELECT p.id, p.produkt, p.tonaz, SUM(sz.waga) as suma_szarz, COUNT(sz.id) as ilosc_szarz
    FROM plan_produkcji p
    LEFT JOIN szarze sz ON p.id = sz.plan_id
    WHERE p.data_planu = '2026-02-02' AND p.sekcja = 'Zasyp'
    GROUP BY p.id, p.produkt, p.tonaz
    ORDER BY p.id
""")

print("\n" + "=" * 90)
print("SZARŻE NA DZISIAJ - PODSUMOWANIE")
print("=" * 90)
print("Plan | Produkt                 | Plan (tonaz) | Wykonanie (szarże) | Ilość szarż")
print("-" * 90)

total = 0
for row in cursor.fetchall():
    plan_id, produkt, plan_waga, suma_szarz, ilosc = row
    suma_szarz = suma_szarz or 0
    ilosc = ilosc or 0
    total += suma_szarz
    print(f"{plan_id:3} | {produkt:20} | {plan_waga:12.0f} | {suma_szarz:18.0f} | {ilosc:11}")

print("-" * 90)
print(f"RAZEM WYKONANIE SZARŻ: {total:.0f} kg")

conn.close()
