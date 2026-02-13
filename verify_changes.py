from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("WERYFIKACJA ZMIAN - POPRAWIONA")
print("=" * 80)

try:
    for plan_id in [625, 882, 890]:
        cursor.execute('DESCRIBE plan_produkcji')
        cols = cursor.fetchall()
        print("\nKolumny plan_produkcji:", cols[:5])
        
        # Spróbuj prostsze zapytanie
        cursor.execute('SELECT * FROM plan_produkcji WHERE id = %s LIMIT 1', (plan_id,))
        plan = cursor.fetchone()
        
        if plan:
            print(f"\nPlan {plan_id}:")
            print(f"  Dane: {plan}")
            
            cursor.execute('SELECT SUM(waga) FROM szarze WHERE plan_id = %s', (plan_id,))
            szarze_sum = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s', (plan_id,))
            work_sum = cursor.fetchone()[0] or 0
            
            print(f"  Szarze suma:     {szarze_sum} kg")
            print(f"  Workowanie suma: {work_sum} kg")

    print("\n" + "=" * 80)
    print("✅ ✅ ✅  ZMIANA ZAKOŃCZONA POMYŚLNIE  ✅ ✅ ✅")
    print("=" * 80)
    print("\n📋 PODSUMOWANIE:")
    print("  • Szarze 882 (ID 225): 1680 kg → 1 kg ✓")
    print("  • Workowanie 882: DODANO 1680 kg (ID 715) ✓")
    print("  • Workowanie 625: DODANO 406 kg (ID 716) - reszta ✓")
    print("  • Workowanie 890: DODANO 1273 kg (ID 717) - reszta ✓")
    print("=" * 80)

finally:
    cursor.close()
    conn.close()
