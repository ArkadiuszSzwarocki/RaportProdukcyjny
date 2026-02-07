from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# List all tables
cursor.execute("SHOW TABLES")
tables = cursor.fetchall()

print("All tables in database:")
for table in tables:
    table_name = table[0]
    print(f"  - {table_name}")
    
    # Check each table with login info
    if 'login' in table_name.lower() or 'user' in table_name.lower():
        cursor.execute(f"DESC {table_name}")
        cols = cursor.fetchall()
        print(f"    Columns: {', '.join(c[0] for c in cols[:5])}")

conn.close()
