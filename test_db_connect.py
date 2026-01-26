import os
from dotenv import load_dotenv
import pymysql

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

host = os.getenv('DB_HOST')
port = int(os.getenv('DB_PORT') or 3307)
user = os.getenv('DB_USER')
password = os.getenv('DB_PASS') or os.getenv('DB_PASSWORD')
db = os.getenv('DB_NAME')

print("Connecting to:", host, port, user, db)
try:
    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db, connect_timeout=5)
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        print("OK, SELECT 1 ->", cur.fetchone())
    conn.close()
except Exception as e:
    print("Connection error:", repr(e))