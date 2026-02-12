from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print('='*100)
print('POPRAWA SZARZY ID 225 - PLAN 882 (AGRO MILK TOP - BUFOR)')
print('='*100)

try:
    # Pokaż przed
    print('\nBEFORE:')
    cursor.execute('SELECT id, plan_id, waga, status FROM szarze WHERE id = 225')
    before = cursor.fetchone()
    print(f'  Szarze ID {before[0]}, Plan ID {before[1]}, Waga: {before[2]} kg, Status: {before[3]}')

    # Popraw
    print('\nPoprawianie szarży ID 225: 1 kg → 1680 kg')
    cursor.execute('UPDATE szarze SET waga = 1680 WHERE id = 225')

    # Pokaż po
    print('\nAFTER:')
    cursor.execute('SELECT id, plan_id, waga, status FROM szarze WHERE id = 225')
    after = cursor.fetchone()
    print(f'  Szarze ID {after[0]}, Plan ID {after[1]}, Waga: {after[2]} kg, Status: {after[3]}')

    conn.commit()
    print('\n' + '='*100)
    print('WERYFIKACJA FINALNA:')
    print('='*100)
    
    cursor.execute('''
        SELECT p.id, p.produkt, p.tonaz, SUM(s.waga) as szarze_sum
        FROM plan_produkcji p
        LEFT JOIN szarze s ON p.id = s.plan_id
        WHERE p.id IN (625, 890, 882)
        GROUP BY p.id
        ORDER BY p.id
    ''')
    
    for row in cursor.fetchall():
        plan_kg = row[2]
        szarze_kg = row[3] if row[3] else 0
        diff = szarze_kg - plan_kg
        status = '✓ OK' if abs(diff) < 1 else f'Roznica: {diff} kg'
        print(f'Plan {row[0]}: {row[1]:25} | Plan: {plan_kg:8.0f} kg | Szarze: {szarze_kg:8.0f} kg | {status}')

except Exception as e:
    print(f'BLAD: {e}')
    conn.rollback()
finally:
    cursor.close()
    conn.close()
