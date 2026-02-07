from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check distinct sekcja values
cursor.execute("SELECT DISTINCT sekcja FROM plan_produkcji")
sections = cursor.fetchall()

print("Distinct sekcja values in database:")
for section in sections:
    print(f"  '{section[0]}'")

conn.close()
