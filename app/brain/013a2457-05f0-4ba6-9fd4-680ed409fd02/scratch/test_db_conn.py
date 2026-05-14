
from app.db import get_db_connection
try:
    print("Connecting to DB...")
    conn = get_db_connection()
    cursor = conn.cursor()
    print("Checking tables...")
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"Found {len(tables)} tables.")
    cursor.close()
    conn.close()
    print("Success.")
except Exception as e:
    print(f"Error: {e}")
