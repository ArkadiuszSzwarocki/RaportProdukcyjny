from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdzenie czy są niezrealizowane plany na 04.03
cursor.execute("""
    SELECT id, produkt, tonaz, tonaz_rzeczywisty, status
    FROM plan_produkcji
    WHERE DATE(data_planu) = '2026-03-04'
    AND sekcja = 'Agro'
    ORDER BY id
""")

plans = cursor.fetchall()
print("PLANY NA 04.03:")
for plan in plans:
    plan_id, produkt, plan_kg, wykonanie_kg, status = plan
    is_incomplete = (status == 'zakonczone' and wykonanie_kg < plan_kg)
    print(f"  ID={plan_id}, produkt={produkt}")
    print(f"    Plan: {plan_kg}kg, Wykonanie: {wykonanie_kg}kg, Status: {status}")
    print(f"    Czy niezrealizowany: {is_incomplete}")

# Czy są jakiekolwiek niezrealizowane na 04.03
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji
    WHERE DATE(data_planu) = '2026-03-04'
    AND sekcja = 'Agro'
    AND status = 'zakonczone'
    AND tonaz_rzeczywisty < tonaz
""")
count_incomplete = cursor.fetchone()[0]
print(f"\nIlość niezrealizowanych planów na 04.03: {count_incomplete}")
print(f"Czy widoczny przycisk: {'TAK' if count_incomplete > 0 else 'NIE'}")

cursor.close()
conn.close()
