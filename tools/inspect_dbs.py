import mysql.connector
import os
from dotenv import load_dotenv

# Load environmental variables
load_dotenv(override=True)

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', 3307))
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

print(f"Connecting to {host}:{port}...")

try:
    # Try connecting to MySQL to list databases
    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password
    )
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    databases = [d[0] for d in cursor.fetchall()]
    print("Available databases:", databases)
    conn.close()
except Exception as e:
    print("Error listing databases:", e)
