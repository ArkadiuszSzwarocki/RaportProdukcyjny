from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("PLANY 896 i 897 - BIEŻĄCY STAN")
print("=" * 80)

for plan_id in [896, 897]:
    print(f"\nPLAN {plan_id}:")
    
    # Plan
    cursor.execute('''
        SELECT id, produkt, tonaz, status, sekcja
        FROM plan_produkcji WHERE id = %s
    ''', (plan_id,))
    plan = cursor.fetchone()
    
    if plan:
        print(f"  ID: {plan[0]}")
        print(f"  Produkt: {plan[1]}")
        print(f"  Tonaz: {plan[2]} kg")
        print(f"  Status: {plan[3]}")
        print(f"  Sekcja: {plan[4]}")
        
        # Szarze
        cursor.execute('SELECT SUM(waga) FROM szarze WHERE plan_id = %s', (plan_id,))
        szarze = cursor.fetchone()[0] or 0
        print(f"  Szarze: {szarze} kg")
        
        # Workowanie
        cursor.execute('SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s', (plan_id,))
        work = cursor.fetchone()[0] or 0
        print(f"  Workowanie: {work} kg")
        
        # Bufor count
        cursor.execute('SELECT COUNT(*) FROM bufor WHERE zasyp_id IN (SELECT id FROM szarze WHERE plan_id = %s)', (plan_id,))
        buf = cursor.fetchone()[0]
        print(f"  Bufor entries: {buf}")
    else:
        print(f"  ✗ PLAN NIE ISTNIEJE!")

cursor.close()
conn.close()
