from app.db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor()

# Check max ID
cursor.execute("SELECT MAX(id) FROM wnioski_wolne")
max_id = cursor.fetchone()[0]
print(f"Max ID in wnioski_wolne: {max_id}")

# List all records with their status
cursor.execute("SELECT id, status FROM wnioski_wolne ORDER BY id DESC LIMIT 10")
results = cursor.fetchall()
print("\nLast 10 records:")
for id_, status in results:
    print(f"  ID {id_}: {status}")

conn.close()
