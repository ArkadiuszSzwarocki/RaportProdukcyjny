import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', 3307))
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

def check_collisions():
    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='biblioteka'
        )
        cursor = conn.cursor()
        
        # Check plan_produkcji
        psd_ids = [64, 65, 66, 67]
        cursor.execute(f"SELECT id FROM plan_produkcji WHERE id IN ({','.join(map(str, psd_ids))})")
        existing_psd = [r[0] for r in cursor.fetchall()]
        print("Existing plan_produkcji IDs in target (PSD):", existing_psd)
        
        # Check plan_produkcji_agro
        agro_ids = [32, 33]
        cursor.execute(f"SELECT id FROM plan_produkcji_agro WHERE id IN ({','.join(map(str, agro_ids))})")
        existing_agro = [r[0] for r in cursor.fetchall()]
        print("Existing plan_produkcji_agro IDs in target (AGRO):", existing_agro)
        
        # Check max IDs in target
        cursor.execute("SELECT MAX(id) FROM plan_produkcji")
        print("Max ID in target plan_produkcji (PSD):", cursor.fetchone()[0])
        
        cursor.execute("SELECT MAX(id) FROM plan_produkcji_agro")
        print("Max ID in target plan_produkcji_agro (AGRO):", cursor.fetchone()[0])
        
        conn.close()
    except Exception as e:
        print("Error checking collisions:", e)

check_collisions()
