from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
try:
    cur.execute("CREATE TEMPORARY TABLE test_date (d DATE)")
    # Test 11.05.2026
    cur.execute("INSERT INTO test_date VALUES ('11.05.2026')")
    cur.execute("SELECT d FROM test_date")
    print('Inserted 11.05.2026 result:', cur.fetchall())
except Exception as e:
    print('Error:', e)
