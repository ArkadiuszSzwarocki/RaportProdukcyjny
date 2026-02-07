from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check table structure
cursor.execute("DESC pracownicy")
columns = cursor.fetchall()

print("Table structure (pracownicy):")
for col in columns:
    print(f"  {col[0]:20s} {col[1]}")

conn.close()
