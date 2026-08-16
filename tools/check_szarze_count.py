import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db import get_db_connection

try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM szarze WHERE status=%s", ("zarejestrowana",))
    res = cur.fetchone()
    print(res)
    cur.close()
    conn.close()
except Exception as e:
    import traceback
    traceback.print_exc()
    print('ERROR:', e)
