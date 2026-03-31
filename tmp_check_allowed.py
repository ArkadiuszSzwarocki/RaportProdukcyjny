import json
from app.db import get_db_connection, get_table_name
from datetime import date
from app.services.dashboard_service import DashboardService

dzisiaj = date(2026, 3, 31)
aktywna_linia = 'PSD'
# Mock application object for logging
class MockApp:
    def __init__(self):
        self.logger = type('Logger', (), {'info': print, 'error': print})()
app = MockApp()

# Replicate routes_main.py logic
plan_dnia, palety_mapa, suma_plan, suma_wykonanie = DashboardService.get_production_plans(dzisiaj, 'Workowanie', linia=aktywna_linia)
work_first_map = DashboardService.get_first_workowanie_map(dzisiaj, linia=aktywna_linia)

allowed_work_start_ids = set()
try:
    table_bufor = get_table_name('bufor', aktywna_linia)
    table_plan = get_table_name('plan_produkcji', aktywna_linia)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(f"""
        SELECT MIN(b.kolejka) as global_min_queue
        FROM {table_bufor} b
        WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
          AND EXISTS (
              SELECT 1 FROM {table_plan} w
              WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
                AND w.produkt = b.produkt AND DATE(w.data_planu) = DATE(b.data_planu)
          )
    """, (dzisiaj,))
    
    result = cursor.fetchone()
    global_min_queue = result[0] if result and result[0] is not None else None
    print(f"Global min queue: {global_min_queue}")
    
    if global_min_queue is not None:
        cursor.execute(f"""
            SELECT DISTINCT produkt
            FROM {table_bufor} 
            WHERE DATE(data_planu) = %s AND status = 'aktywny' AND kolejka = %s
        """, (dzisiaj, global_min_queue))
        products_with_min_queue = [row[0] for row in cursor.fetchall()]
        print(f"Products with min queue: {products_with_min_queue}")
        for prod in products_with_min_queue:
            if prod in work_first_map:
                allowed_work_start_ids.add(work_first_map[prod])
                print(f"Adding allowed ID: {work_first_map[prod]} for {prod}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")

print(f"Final allowed_work_start_ids: {allowed_work_start_ids}")

# Let's compare with actual plan IDs
print("\nActual Workowanie plans for today:")
for p in plan_dnia:
    print(f"ID:{p[0]} | Prod:{p[1]} | Status:{p[3]}")
