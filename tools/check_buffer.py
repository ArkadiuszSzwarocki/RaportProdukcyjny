from db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor()
# Sprawdz plany Workowanie dla produktu 'test'
cursor.execute("SELECT id, produkt, tonaz, sekcja, status, tonaz_rzeczywisty FROM plan_produkcji WHERE produkt='test' AND data_planu='2026-02-01' ORDER BY sekcja, id")
print("\n=== PLANY DLA PRODUKTU 'test' NA 2026-02-01 ===")
for row in cursor.fetchall():
    print(f'ID={row[0]}, Produkt={row[1]}, Tonaz={row[2]}, Sekcja={row[3]}, Status={row[4]}, TonazRzeczywisty={row[5]}')
conn.close()
