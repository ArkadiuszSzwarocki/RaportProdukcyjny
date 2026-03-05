from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
count_04 = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
count_05 = cursor.fetchone()[0]

cursor.close()
conn.close()

print(f'Bufor 04.03 = {count_04}')
print(f'Bufor 05.03 = {count_05}')
