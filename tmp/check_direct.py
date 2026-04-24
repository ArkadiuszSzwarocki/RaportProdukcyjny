import sys
import os

# Add root to pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import DB_CONFIG
import pymysql

try:
    print(f"Connecting to DB with: user={DB_CONFIG.get('user')}, host={DB_CONFIG.get('host')}, port={DB_CONFIG.get('port')}")
    conn = pymysql.connect(
        host=DB_CONFIG.get('host', 'localhost'),
        port=DB_CONFIG.get('port', 3306),
        user=DB_CONFIG.get('user', 'root'),
        password=DB_CONFIG.get('password', ''),
        database=DB_CONFIG.get('database', 'raportprodukcyjny'),
        charset=DB_CONFIG.get('charset', 'utf8mb4'),
        cursorclass=pymysql.cursors.DictCursor
    )
    
    with conn.cursor() as cursor:
        print("=== BUFOR AGRO STATUS ===")
        cursor.execute("SELECT b.id, b.produkt, b.kolejka, b.status, b.data_planu FROM bufor_agro b WHERE b.status = 'aktywny' ORDER BY b.kolejka ASC")
        bufor = cursor.fetchall()
        for b in bufor:
            print(f"[{b['kolejka']}] {b['produkt']} | Status: {b['status']} | Data: {b['data_planu']}")
        if not bufor: print("No active items in bufor_agro.")
            
        print("\n=== PLAN AGRO (Workowanie) ===")
        cursor.execute("SELECT id, produkt, status, data_planu FROM plan_produkcji_agro WHERE sekcja = 'Workowanie' AND status IN ('zaplanowane', 'w toku') AND DATE(data_planu) = CURDATE()")
        plany = cursor.fetchall()
        for p in plany:
            print(f"ID:{p['id']} | {p['produkt']} | Status: {p['status']} | Data: {p['data_planu']}")
        if not plany: print("No workowanie plans for today.")

        print("\n=== MIN QUEUE CHECK ===")
        cursor.execute("""
            SELECT MIN(b.kolejka) as global_min_queue
            FROM bufor_agro b
            WHERE DATE(b.data_planu) = CURDATE() AND b.status = 'aktywny'
              AND EXISTS (
                  SELECT 1 FROM plan_produkcji_agro w
                  WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
                    AND w.produkt = b.produkt AND w.data_planu = b.data_planu
              )
        """)
        res = cursor.fetchone()
        print("global_min_queue limit is:", res['global_min_queue'] if res else "None")
        
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
