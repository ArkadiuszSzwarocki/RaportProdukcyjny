from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("NAPRAWA - USUWANIE BŁĘDNYCH WPISÓW I DODAWANIE PRAWIDŁOWYCH")
print("=" * 80)

try:
    # Usunąć błędne wpiski (715, 716, 717)
    print("\n1. USUWANIE BŁĘDNYCH WPISÓW...")
    cursor.execute('DELETE FROM palety_workowanie WHERE id IN (715, 716, 717)')
    conn.commit()
    print(f"   ✓ Usunięto 3 błędne wpisy (ID 715, 716, 717)")
    
    # Dodać prawidłowe wpiski
    print("\n2. DODAWANIE PRAWIDŁOWYCH WPISÓW...")
    
    # Plan 882: 1680 kg
    cursor.execute('''
        INSERT INTO palety_workowanie (plan_id, waga, status, data_dodania)
        VALUES (%s, %s, %s, NOW())
    ''', (882, 1680, 'zarejestowana'))
    conn.commit()
    cursor.execute('SELECT LAST_INSERT_ID()')
    id_882 = cursor.fetchone()[0]
    print(f"   ✓ Plan 882: 1680 kg (ID {id_882})")
    
    # Plan 625: 406 kg
    cursor.execute('''
        INSERT INTO palety_workowanie (plan_id, waga, status, data_dodania)
        VALUES (%s, %s, %s, NOW())
    ''', (625, 406, 'zarejestowana'))
    conn.commit()
    cursor.execute('SELECT LAST_INSERT_ID()')
    id_625 = cursor.fetchone()[0]
    print(f"   ✓ Plan 625: 406 kg (ID {id_625})")
    
    # Plan 890: 1273 kg
    cursor.execute('''
        INSERT INTO palety_workowanie (plan_id, waga, status, data_dodania)
        VALUES (%s, %s, %s, NOW())
    ''', (890, 1273, 'zarejestowana'))
    conn.commit()
    cursor.execute('SELECT LAST_INSERT_ID()')
    id_890 = cursor.fetchone()[0]
    print(f"   ✓ Plan 890: 1273 kg (ID {id_890})")
    
    # WERYFIKACJA
    print("\n" + "=" * 80)
    print("WERYFIKACJA NAPRAWY")
    print("=" * 80)
    
    for plan_id, expected_waga in [(882, 1680), (625, 406), (890, 1273)]:
        cursor.execute('SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s', (plan_id,))
        total = cursor.fetchone()[0] or 0
        status = "✓ OK" if total == expected_waga else f"✗ BŁĄD (oczekiwano {expected_waga})"
        print(f"Plan {plan_id}: {total} kg  {status}")
    
    print("\n" + "=" * 80)
    print("✅ NAPRAWA ZAKOŃCZONA - TERAZ ZRESTARTUJ APP.PY")
    print("=" * 80)

except Exception as e:
    conn.rollback()
    print(f"\n❌ BŁĄD: {e}")
finally:
    cursor.close()
    conn.close()
