from app.db import get_db_connection
from datetime import datetime

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("PLAN 882 - KOMPLEKSNA ZMIANA")
print("=" * 80)

try:
    # 1. Cofnąć szarze 882 z 1680 kg na 1 kg
    print("\n1. ZMIANA SZARZE 882...")
    cursor.execute('SELECT waga FROM szarze WHERE id = 225')
    old_waga = cursor.fetchone()[0]
    
    cursor.execute('UPDATE szarze SET waga = 1 WHERE id = 225')
    conn.commit()
    print(f"   ✓ Szarze ID 225: {old_waga} kg → 1 kg")
    
    # 2. Dodać workowanie dla planu 882: 1680 kg
    print("\n2. DODANIE WORKOWANIA PLAN 882...")
    cursor.execute('''
        INSERT INTO palety_workowanie (plan_id, waga, status, data_dodania)
        VALUES (%s, %s, %s, %s)
    ''', (882, 1680, 'zarejestowana', datetime.now()))
    conn.commit()
    cursor.execute('SELECT LAST_INSERT_ID()')
    new_id_882 = cursor.fetchone()[0]
    print(f"   ✓ Nowe workowanie plan 882: ID {new_id_882} | 1680 kg")
    
    # 3. Dodać workowanie dla planu 625: 406 kg
    print("\n3. DODANIE WORKOWANIA PLAN 625...")
    cursor.execute('''
        INSERT INTO palety_workowanie (plan_id, waga, status, data_dodania)
        VALUES (%s, %s, %s, %s)
    ''', (625, 406, 'zarejestowana', datetime.now()))
    conn.commit()
    cursor.execute('SELECT LAST_INSERT_ID()')
    new_id_625 = cursor.fetchone()[0]
    print(f"   ✓ Nowe workowanie plan 625: ID {new_id_625} | 406 kg (reszta)")
    
    # 4. Dodać workowanie dla planu 890: 1273 kg
    print("\n4. DODANIE WORKOWANIA PLAN 890...")
    cursor.execute('''
        INSERT INTO palety_workowanie (plan_id, waga, status, data_dodania)
        VALUES (%s, %s, %s, %s)
    ''', (890, 1273, 'zarejestowana', datetime.now()))
    conn.commit()
    cursor.execute('SELECT LAST_INSERT_ID()')
    new_id_890 = cursor.fetchone()[0]
    print(f"   ✓ Nowe workowanie plan 890: ID {new_id_890} | 1273 kg (reszta)")
    
    # WERYFIKACJA
    print("\n" + "=" * 80)
    print("WERYFIKACJA - STAN PO ZMIANACH")
    print("=" * 80)
    
    for plan_id in [625, 882, 890]:
        cursor.execute('SELECT produkt, tonaz FROM plan_produkcji WHERE id = %s', (plan_id,))
        plan = cursor.fetchone()
        
        cursor.execute('SELECT SUM(waga) FROM szarze WHERE plan_id = %s', (plan_id,))
        szarze_sum = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s', (plan_id,))
        work_sum = cursor.fetchone()[0] or 0
        
        status = "✓ OK" if szarze_sum > 0 else "⚠ BRAK"
        print(f"\nPlan {plan_id}: {plan[1]}")
        print(f"  Plan tonaz:      {plan[2]} kg")
        print(f"  Szarze suma:     {szarze_sum} kg  {status}")
        print(f"  Workowanie suma: {work_sum} kg")
    
    print("\n" + "=" * 80)
    print("✅ WSZYSTKIE ZMIANY ZATWIERDZONO")
    print("=" * 80)

except Exception as e:
    conn.rollback()
    print(f"\n❌ BŁĄD: {e}")
finally:
    cursor.close()
    conn.close()
