from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print('='*100)
print('DIAGNOZA: TONAZ = KG (nie TONY)')
print('='*100)

plan_ids = [625, 890, 882]

total_plan = 0
total_szarze = 0
total_shortage = 0

for plan_id in plan_ids:
    cursor.execute('SELECT id, produkt, tonaz, status FROM plan_produkcji WHERE id = %s', (plan_id,))
    plan = cursor.fetchone()
    
    cursor.execute('SELECT SUM(waga) FROM szarze WHERE plan_id = %s', (plan_id,))
    szarze = cursor.fetchone()
    szarze_kg = szarze[0] if szarze[0] else 0
    
    plan_kg = plan[2]
    shortage = plan_kg - szarze_kg
    
    total_plan += plan_kg
    total_szarze += szarze_kg
    total_shortage += shortage
    
    pct = 0 if plan_kg == 0 else shortage/plan_kg*100
    print(f'\nPlan ID {plan_id}: {plan[1]}')
    print(f'  Plan: {plan_kg:10.0f} kg')
    print(f'  Szarze: {szarze_kg:10.0f} kg')
    print(f'  Roznica: {shortage:10.0f} kg ({pct:6.1f}%)')

print()
print('='*100)
print(f'RAZEM PLAN: {total_plan:10.0f} kg')
print(f'RAZEM SZARZE: {total_szarze:10.0f} kg')
print(f'RAZEM BRAKUJE: {total_shortage:10.0f} kg')
print('='*100)

# Sprawdz czy sa gdzies szarze ktorym brakuje plan_id
print()
print('SZARZE BEZ PRZYPISANEGO PLANU (moga byc "sierocinkami"):')
cursor.execute('SELECT COUNT(*), SUM(waga) FROM szarze WHERE plan_id IS NULL OR plan_id = 0')
orphans = cursor.fetchone()
print(f'  Sierocin: {orphans[0]}, Suma: {orphans[1]} kg')

# Sprawdz szczegoly dla bufora
print()
print('='*100)
print('SZCZEGOLOWA ANALIZA BUFORA (Plan 882 - 1680 kg):')
print('='*100)
cursor.execute('''
    SELECT id, produkt, tonaz, status, zasyp_id
    FROM plan_produkcji 
    WHERE id = 882
''')
plan_882 = cursor.fetchone()
print(f'Plan 882: {plan_882[1]}, Tonaz: {plan_882[2]} kg, Status: {plan_882[3]}, Zasyp_id: {plan_882[4]}')

# Szarze dla 882
cursor.execute('SELECT id, waga, status FROM szarze WHERE plan_id = 882')
szarze_882 = cursor.fetchall()
print(f'Szarze dla planu 882: {len(szarze_882)} wpisow')
for s in szarze_882:
    print(f'  ID: {s[0]}, Waga: {s[1]} kg, Status: {s[2]}')

cursor.close()
conn.close()
