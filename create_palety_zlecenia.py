#!/usr/bin/env python
"""
Rozdziel każde zlecenie Zasypu na palety po 1000 kg
z logiką zaokrąglania końcówek:
- końcówka ≤ 205 kg → zaokrąglij (dodaj do poprzedniej palety)
- końcówka > 205 kg → zaakceptuj (osobna paleta)
"""
from app.db import get_db_connection
from datetime import date

def create_palety_for_zlecenie(plan_id, produkt, tonaz_rzeczywisty):
    """
    Stwórz palety dla zlecenia
    """
    wenn_tonaz = tonaz_rzeczywisty or 0
    
    if wenn_tonaz == 0:
        return []
    
    # Podziel na palety po 1000 kg
    full_palety = int(wenn_tonaz // 1000)
    remainder = wenn_tonaz % 1000
    
    palety = []
    
    # Dodaj pełne palety
    for i in range(full_palety):
        palety.append(1000)
    
    # Obsługuj resztę
    if remainder > 0:
        if remainder <= 205:
            # Zaokrąglij - dodaj do ostatniej palety
            if palety:
                palety[-1] += remainder
            else:
                # Jeśli nie ma pełnych palet, utwórz jedną
                palety.append(remainder)
        else:
            # Zaakceptuj końcówkę
            palety.append(remainder)
    
    return palety

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()

print(f'\n{"="*100}')
print(f'GENERATOR PALETEK DLA ZLECEŃ ZASYPU ({today})')
print(f'{"="*100}\n')

# Pobierz wszystkie plany Zasypu dzisiaj
cursor.execute('''
    SELECT id, produkt, tonaz_rzeczywisty, sekcja
    FROM plan_produkcji
    WHERE DATE(data_planu)=%s AND sekcja='Zasyp' AND is_deleted=0
    ORDER BY produkt
''', (today,))

plans = cursor.fetchall()

total_palety_created = 0

for p in plans:
    plan_id = p['id']
    produkt = p['produkt']
    tonaz = p['tonaz_rzeczywisty'] or 0
    
    # Wygeneruj plan paletek
    palety_weights = create_palety_for_zlecenie(plan_id, produkt, tonaz)
    
    print(f'\n📦 {produkt}:')
    print(f'   Tonaz rzeczywisty: {tonaz:.0f} kg')
    print(f'   Plan paletek: {len(palety_weights)} szt')
    
    for i, waga in enumerate(palety_weights, 1):
        print(f'     Paleta {i}: {waga:.0f} kg')
    
    # Sprawdź czy już są palety - jeśli nie, stwórz
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM palety_workowanie WHERE plan_id=%s",
        (plan_id,)
    )
    existing = cursor.fetchone()
    
    if existing and existing['cnt'] > 0:
        print(f'   ⚠️  Palety już istnieją ({existing["cnt"]} szt) - pominięto')
    else:
        # Stwórz palety
        for waga in palety_weights:
            cursor.execute(
                "INSERT INTO palety_workowanie (plan_id, waga, status) VALUES (%s, %s, %s)",
                (plan_id, waga, 'oczekuje')
            )
            total_palety_created += 1
        
        print(f'   ✅ Utworzono {len(palety_weights)} palet')

conn.commit()
cursor.close()
conn.close()

print(f'\n{"="*100}')
print(f'✅ KOMPLETNE!')
print(f'Utworzono łącznie: {total_palety_created} palet')
print(f'{"="*100}\n')
