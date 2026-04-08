from app.db import get_db_connection
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = [t[0] for t in cursor.fetchall()]
    print("Tables:", tables)
    for table in ['plan_produkcji_agro', 'szarze_agro', 'dosypki_agro', 'palety_agro']:
        if table in tables:
            print(f"Table {table} exists.")
            cursor.execute(f"DESCRIBE {table}")
            print(f"Structure of {table}:", cursor.fetchall())
        else:
            print(f"Table {table} MISSING!")
    conn.close()
except Exception as e:
    print("Error:", e)
