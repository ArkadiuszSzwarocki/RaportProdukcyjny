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
        
        # Get active links
        cursor.execute("""
            SELECT ap.id, ap.opakowanie_id, ap.stan_poczatkowy, o.nazwa
            FROM agro_plan_opakowania ap
            JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
            WHERE ap.plan_id = %s AND ap.is_active = TRUE
        """, (plan_id,))
        active_links = cursor.fetchall()
        
        for al in active_links:
            # Check if there is already a wsadzenie record (zuzyte_worki = 0)
            cursor.execute("""
                SELECT id FROM agro_workowanie_rozliczenie
                WHERE plan_id = %s AND opakowanie_id = %s AND zuzyte_worki = 0
            """, (plan_id, al['opakowanie_id']))
            if cursor.fetchone():
                print(f"Roll '{al['nazwa']}' already has a wsadzenie record.")
                continue
                
            print(f"Inserting wsadzenie log for active roll '{al['nazwa']}' (ID: {al['opakowanie_id']}) with {al['stan_poczatkowy']} pcs.")
            cursor.execute("""
                INSERT INTO agro_workowanie_rozliczenie (
                    plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                    stan_przed, wyprodukowano_szt, szt_na_palecie, palety_kg_wykonane, zuzyte_worki, stan_po, autor_login
                ) VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, 'System')
            """, (
                plan_id, plan['data_planu'], plan['produkt'], al['opakowanie_id'], al['nazwa'],
                al['stan_poczatkowy'], al['stan_poczatkowy']
            ))
            
        conn.commit()
        print("Success!")
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
