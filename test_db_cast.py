from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
try:
    cur.execute("SELECT CAST('11.05.2026' AS DATE)")
    print('11.05.2026 CAST:', cur.fetchall())
except Exception as e:
    print('CAST Error:', e)

try:
    cur.execute("SELECT STR_TO_DATE('11.05.2026', '%d.%m.%Y')")
    print('11.05.2026 STR_TO_DATE:', cur.fetchall())
except Exception as e:
    print('STR_TO_DATE Error:', e)
