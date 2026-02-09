from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Weź pierwszy plan dzisiaj
cursor.execute("""
    SELECT id FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    LIMIT 1
""", (date.today(),))

result = cursor.fetchone()
if result:
    plan_id = result[0]
    
    # Wstaw test wartość
    cursor.execute("UPDATE plan_produkcji SET uszkodzone_worki = 123 WHERE id = %s", (plan_id,))
    conn.commit()
    
    # Sprawdź
    cursor.execute("SELECT uszkodzone_worki FROM plan_produkcji WHERE id = %s", (plan_id,))
    val = cursor.fetchone()[0]
    
    print(f"✓ Ustawiłem plan ID={plan_id} na uszkodzone_worki={val}")
    print("\nSpradzaj w przeglądarce - kolumna 'Uszkodzone Worki' powinna pokazać 123!")
else:
    print("Brak planów na dzisiaj")

conn.close()
