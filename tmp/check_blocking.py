import sys
import os

# Set up paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.factory import create_app
from app.db import get_db_connection

app = create_app()

with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    print("=== GLOBAL MIN QUEUE (from bufor_agro) ===")
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
    print("Global MIN queue:", res['global_min_queue'] if res else None)
    
    print("\n=== BUFOR AGRO ===")
    cursor.execute("""
        SELECT b.id, b.produkt, b.kolejka, b.status, b.data_planu
        FROM bufor_agro b
        WHERE b.status = 'aktywny' AND DATE(b.data_planu) = CURDATE()
        ORDER BY b.kolejka ASC
    """)
    bufor = cursor.fetchall()
    for b in bufor:
        print(f"[{b['kolejka']}] {b['produkt']} (status: {b['status']})")
        
    print("\n=== PLAN PRODUKCJI AGRO (Workowanie) ===")
    cursor.execute("""
        SELECT id, produkt, sekcja, status, data_planu
        FROM plan_produkcji_agro
        WHERE sekcja = 'Workowanie' AND status IN ('zaplanowane', 'w toku')
          AND DATE(data_planu) = CURDATE()
    """)
    plany = cursor.fetchall()
    for p in plany:
        print(f"[{p['id']}] {p['produkt']} (status: {p['status']})")

    cursor.close()
    conn.close()
