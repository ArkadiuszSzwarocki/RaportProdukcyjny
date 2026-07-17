from app.db import get_db_connection

def reset_folio():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Znajdź aktywne zlecenie Workowanie (lub ostatnie)
    cursor.execute("SELECT id FROM plan_produkcji_agro WHERE sekcja = 'Workowanie' ORDER BY id DESC LIMIT 1")
    plan = cursor.fetchone()
    if plan:
        plan_id = plan['id']
        print(f'Resetting for plan_id: {plan_id}')
        
        # 1. Przywróć stan magazynowy dla rolek, które były pobrane na to zlecenie
        cursor.execute('SELECT opakowanie_id, stan_poczatkowy FROM agro_plan_opakowania WHERE plan_id = %s', (plan_id,))
        opakowania = cursor.fetchall()
        for o in opakowania:
            cursor.execute('UPDATE magazyn_opakowania SET stan_magazynowy = stan_magazynowy + %s WHERE id = %s', (o['stan_poczatkowy'], o['opakowanie_id']))
            print(f"Restored {o['stan_poczatkowy']} to packaging {o['opakowanie_id']}")
        
        # 2. Usuń historię rozliczeń folii dla planu
        cursor.execute('DELETE FROM agro_workowanie_rozliczenie WHERE plan_id = %s', (plan_id,))
        print("Deleted agro_workowanie_rozliczenie history")
        
        # 3. Usuń przypisania folii dla planu
        cursor.execute('DELETE FROM agro_plan_opakowania WHERE plan_id = %s', (plan_id,))
        print("Deleted agro_plan_opakowania active rolls")
        
        # 4. Wyzeruj uszkodzone worki w planie
        cursor.execute('UPDATE plan_produkcji_agro SET uszkodzone_worki = 0 WHERE id = %s', (plan_id,))
        print("Reset uszkodzone_worki in plan")
        
        conn.commit()
        print('✅ Foil history completely cleared. You can start from zero now.')
    else:
        print('No plan found.')
    conn.close()

if __name__ == '__main__':
    reset_folio()
