from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print('='*100)
print('KOREKTA PLANÓW AGRO MILK TOP')
print('='*100)

try:
    # PLAN 625: 3000 → 3440
    print('\n[1] Korygowanie Plan ID 625: 3000 kg → 3440 kg')
    cursor.execute('SELECT id, produkt, tonaz FROM plan_produkcji WHERE id = 625')
    old = cursor.fetchone()
    print(f'  Przed: ID {old[0]}, {old[1]}, {old[2]} kg')
    
    cursor.execute('UPDATE plan_produkcji SET tonaz = 3440 WHERE id = 625')
    
    cursor.execute('SELECT id, produkt, tonaz FROM plan_produkcji WHERE id = 625')
    new = cursor.fetchone()
    print(f'  Po:    ID {new[0]}, {new[1]}, {new[2]} kg ✓')

    # PLAN 890: 10000 → 10778
    print('\n[2] Korygowanie Plan ID 890: 10000 kg → 10778 kg')
    cursor.execute('SELECT id, produkt, tonaz FROM plan_produkcji WHERE id = 890')
    old = cursor.fetchone()
    print(f'  Przed: ID {old[0]}, {old[1]}, {old[2]} kg')
    
    cursor.execute('UPDATE plan_produkcji SET tonaz = 10778 WHERE id = 890')
    
    cursor.execute('SELECT id, produkt, tonaz FROM plan_produkcji WHERE id = 890')
    new = cursor.fetchone()
    print(f'  Po:    ID {new[0]}, {new[1]}, {new[2]} kg ✓')

    # PLAN 882: Pozostaje 1 kg (resztki - OK)
    print('\n[3] Plan ID 882 - Pozostawić 1 kg (resztki ze spakowania)')
    cursor.execute('SELECT id, produkt, tonaz FROM plan_produkcji WHERE id = 882')
    result = cursor.fetchone()
    print(f'  ID {result[0]}, {result[1]}, {result[2]} kg (bez zmian - resztki) ✓')

    conn.commit()
    print('\n' + '='*100)
    print('PODSUMOWANIE KOREKTY:')
    print('='*100)
    
    # Sprawdzenie finalne
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
        status = '✓ OK' if abs(diff) < 1 else f'⚠️ Roznica: {diff} kg'
        print(f'Plan {row[0]}: {row[1]:25} | Plan: {plan_kg:8.0f} kg | Szarze: {szarze_kg:8.0f} kg | {status}')

except Exception as e:
    print(f'BLAD: {e}')
    conn.rollback()
finally:
    cursor.close()
    conn.close()
