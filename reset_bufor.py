from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Reset - przywróć rekord z 04.03 z powrotem
cursor.execute('''UPDATE bufor SET data_planu = %s WHERE DATE(data_planu) = %s''', ('2026-03-04', '2026-03-05'))
rows = cursor.rowcount
cursor.close()
conn.commit()
conn.close()

print(f'✓ Reset - przywrócono {rows} rekordów na 2026-03-04')
