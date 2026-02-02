import mysql.connector
from config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# Usuń stare paletki z testów (id >= 215)
cursor.execute('DELETE FROM palety_workowanie WHERE id >= 215')
deleted_palety = cursor.rowcount

# Usuń stare plany z Magazynu dla dzisiejszego dnia
cursor.execute("DELETE FROM plan_produkcji WHERE sekcja='Magazyn' AND DATE(data_planu)=CURDATE()")
deleted_plans = cursor.rowcount

conn.commit()
print(f'✓ Usunięto {deleted_palety} palet')
print(f'✓ Usunięto {deleted_plans} planów z Magazynu')
conn.close()
