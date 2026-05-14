from app.db import get_db_connection
print("Connecting to DB...")
try:
    conn = get_db_connection()
    print("Connected!")
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    print("Query executed!")
    conn.close()
    print("Connection closed.")
except Exception as e:
    print(f"Error: {e}")
