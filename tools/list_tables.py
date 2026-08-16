import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', 3307))
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

try:
    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database='biblioteka_testowa'
    )
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = [t[0] for t in cursor.fetchall()]
    print("Tables in biblioteka_testowa:")
    for t in sorted(tables):
        print(f"  {t}")
    conn.close()
except Exception as e:
    print("Error listing tables:", e)
