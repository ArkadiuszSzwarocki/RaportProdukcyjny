import sys
from app.db import get_db_connection

def main():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Find active plan
        cursor.execute("SELECT id, produkt, data_planu FROM plan_produkcji_agro WHERE status='w toku' AND sekcja='Workowanie' ORDER BY real_start DESC LIMIT 1")
        plan = cursor.fetchone()
        if not plan:
            print("No active plan found.")
            return
        
        plan_id = plan['id']
        print(f"Active Plan: #{plan_id} - {plan['produkt']} ({plan['data_planu']})")
        
        # Query agro_plan_opakowania
        cursor.execute("SELECT * FROM agro_plan_opakowania WHERE plan_id = %s", (plan_id,))
        links = cursor.fetchall()
        print("\n--- agro_plan_opakowania ---")
        for link in links:
            print(link)
            
        # Query agro_workowanie_rozliczenie
        cursor.execute("SELECT * FROM agro_workowanie_rozliczenie WHERE plan_id = %s", (plan_id,))
        settlements = cursor.fetchall()
        print("\n--- agro_workowanie_rozliczenie ---")
        for s in settlements:
            print(s)
            
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
