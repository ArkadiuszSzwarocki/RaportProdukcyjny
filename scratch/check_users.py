import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', '3307'))
database = os.getenv('DB_NAME', 'biblioteka')
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

try:
    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset='utf8mb4'
    )
    cursor = conn.cursor(dictionary=True)
    
    # Describe uzytkownicy
    cursor.execute("DESCRIBE uzytkownicy")
    columns = cursor.fetchall()
    print("Columns in 'uzytkownicy':")
    for col in columns:
        print(f"  Field: {col['Field']} | Type: {col['Type']}")
        
    # Get all users
    cursor.execute("SELECT * FROM uzytkownicy")
    rows = cursor.fetchall()
    print("\nUsers:")
    for r in rows:
        print(f"  ID: {r.get('id')} | Login: {r.get('login')} | Rola: {r.get('rola')} | Imie: {r.get('imie')} | Nazwisko: {r.get('nazwisko')}")
        
    conn.close()
except Exception as e:
    print(f"MySQL query error: {e}")
