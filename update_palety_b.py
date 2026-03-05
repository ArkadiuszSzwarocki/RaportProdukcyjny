#!/usr/bin/env python
"""
Zmień podział palet aby pasował do tonaz_rzeczywisty:
- MILK BAND BIAŁE: 1×1000 + 60 kg
- MOM INSTANT: 11×1000 + 206 kg
- HOLENDER: 8×1000 + 420 kg (bez zmian)
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()

# Specyfikacja nowych palet dostosowanych do tonaz_rzeczywisty
palety_spec = {
    'MILK BAND BIAŁE': [1000, 60],
    'MOM INSTANT': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 206],
    'HOLENDER': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 420],
}

print(f'\n{"="*100}')
print(f'DOSTOSOWANIE PODZIAŁU PALET DO tonaz_rzeczywisty ({today})')
print(f'{"="*100}\n')

total_deleted = 0
total_created = 0

for produkt, palety_weights in palety_spec.items():
    # Pobierz plan_id
    cursor.execute(
        "SELECT id, tonaz_rzeczywisty FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja='Zasyp' AND produkt=%s",
        (today, produkt)
    )
    plan = cursor.fetchone()
    
    if not plan:
        print(f'❌ {produkt}: PLAN NIE ZNALEZIONY')
        continue
    
    plan_id = plan['id']
    tonaz = plan['tonaz_rzeczywisty'] or 0
    
    # Sprawdź sumę nowych palet
    new_sum = sum(palety_weights)
    
    print(f'\n📦 {produkt}:')
    print(f'   Tonaz rzeczywisty w DB: {tonaz:.0f} kg')
    print(f'   Nowe palety sum: {new_sum:.0f} kg')
    
    if abs(tonaz - new_sum) > 0.01:
        print(f'   ⚠️  OSTRZEŻENIE: Suma nowych palet ({new_sum:.0f}) != tonaz_rzeczywisty ({tonaz:.0f})')
    else:
        print(f'   ✅ Zgadza się!')
    
    # Usuń stare palety
    cursor.execute("SELECT COUNT(*) as cnt FROM palety_workowanie WHERE plan_id=%s", (plan_id,))
    old_count = cursor.fetchone()['cnt']
    
    if old_count > 0:
        cursor.execute("DELETE FROM palety_workowanie WHERE plan_id=%s", (plan_id,))
        total_deleted += old_count
        print(f'   🗑️  Usunięto {old_count} starych palet')
    
    # Stwórz nowe palety
    for i, waga in enumerate(palety_weights, 1):
        cursor.execute(
            "INSERT INTO palety_workowanie (plan_id, waga, status) VALUES (%s, %s, %s)",
            (plan_id, waga, 'oczekuje')
        )
        total_created += 1
    
    print(f'   ✅ Utworzono {len(palety_weights)} nowych palet:')
    for i, waga in enumerate(palety_weights, 1):
        print(f'      Paleta {i}: {waga:.0f} kg')

conn.commit()
cursor.close()
conn.close()

print(f'\n{"="*100}')
print(f'✅ DOSTOSOWANIE PALET ZAKOŃCZONE')
print(f'Usunięto: {total_deleted} palet')
print(f'Utworzono: {total_created} palet')
print(f'{"="*100}\n')
