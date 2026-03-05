#!/usr/bin/env python
"""
Kompletna operacja:
1. Skopiuj palety z Zasypu do Workowania dla każdego produktu
2. Zaktualizuj bufor
3. Sprawdź stan całego systemu
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()

print(f'\n{"="*100}')
print(f'OPERACJA KOMPLEKSOWA: Palety → Workowanie → Bufor ({today})')
print(f'{"="*100}\n')

# ===== KROK 1: Pobierz mapowania plan_id Zasyp ↔ Workowanie =====
cursor.execute('''
    SELECT produkt, 
           MAX(CASE WHEN sekcja='Zasyp' THEN id END) as zasyp_id,
           MAX(CASE WHEN sekcja='Workowanie' THEN id END) as work_id,
           MAX(CASE WHEN sekcja='Zasyp' THEN tonaz_rzeczywisty END) as zasyp_tonaz
    FROM plan_produkcji
    WHERE DATE(data_planu)=%s AND is_deleted=0
    GROUP BY produkt
''', (today,))

mapowania = cursor.fetchall()

print('MAPOWANIE PRODUKTÓW:')
for m in mapowania:
    produkt = m['produkt']
    zasyp_id = m['zasyp_id']
    work_id = m['work_id']
    print(f'  {produkt:20} | Zasyp_ID={zasyp_id} | Work_ID={work_id}')

# ===== KROK 2: Skopiuj palety z Zasypu do Workowania =====
print(f'\n{"="*100}')
print('KROK 1/3: Kopiowanie palet Zasyp → Workowanie')
print(f'{"="*100}\n')

total_palety_copied = 0

for m in mapowania:
    produkt = m['produkt']
    zasyp_id = m['zasyp_id']
    work_id = m['work_id']
    
    if not zasyp_id or not work_id:
        print(f'⚠️  {produkt}: Brak zasyp_id lub work_id - pominięto')
        continue
    
    # Pobierz palety z Zasypu
    cursor.execute(
        "SELECT id, waga, status FROM palety_workowanie WHERE plan_id=%s",
        (zasyp_id,)
    )
    zasyp_palety = cursor.fetchall()
    
    # Sprawdź czy już są palety na Workowaniu
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM palety_workowanie WHERE plan_id=%s",
        (work_id,)
    )
    existing = cursor.fetchone()
    existing_count = existing['cnt'] if existing else 0
    
    if existing_count > 0:
        print(f'⚠️  {produkt}: Palety już istnieją ({existing_count} szt) - pominięto')
        continue
    
    # Skopiuj palety
    for p in zasyp_palety:
        cursor.execute(
            "INSERT INTO palety_workowanie (plan_id, waga, status) VALUES (%s, %s, %s)",
            (work_id, p['waga'], 'oczekuje')
        )
        total_palety_copied += 1
    
    print(f'✅ {produkt:20} | Skopiowano {len(zasyp_palety)} palet do Workowania')

conn.commit()

print(f'\n✅ Łącznie skopiowano: {total_palety_copied} palet')

# ===== KROK 3: Zaktualizuj tonaz_rzeczywisty na Workowaniu =====
print(f'\n{"="*100}')
print('KROK 2/3: Synchronizacja tonaz_rzeczywisty Workowanie')
print(f'{"="*100}\n')

total_updated = 0

for m in mapowania:
    produkt = m['produkt']
    work_id = m['work_id']
    
    if not work_id:
        continue
    
    # Oblicz sumę palet na Workowaniu
    cursor.execute(
        "SELECT COALESCE(SUM(waga), 0) as suma FROM palety_workowanie WHERE plan_id=%s",
        (work_id,)
    )
    result = cursor.fetchone()
    suma_palet = result['suma'] if result else 0
    
    # Zaktualizuj tonaz_rzeczywisty
    if suma_palet > 0:
        cursor.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = %s WHERE id = %s",
            (suma_palet, work_id)
        )
        total_updated += 1
        print(f'✅ {produkt:20} | Workowanie tonaz_rzeczywisty = {suma_palet:.0f} kg')

conn.commit()

# ===== SPRAWDZENIE STANU =====
print(f'\n{"="*100}')
print('SPRAWDZENIE STANU SYSTEMU')
print(f'{"="*100}\n')

cursor.execute('''
    SELECT sekcja, COUNT(*) as cnt, COALESCE(SUM(tonaz_rzeczywisty), 0) as total_tonaz
    FROM plan_produkcji
    WHERE DATE(data_planu)=%s AND is_deleted=0
    GROUP BY sekcja
''', (today,))

sekcje = cursor.fetchall()

print('STATUS PLANÓW:')
for s in sekcje:
    print(f'  {s["sekcja"]:12} | Planów: {s["cnt"]:2} | Tonaz: {s["total_tonaz"]:10.0f} kg')

cursor.execute('''
    SELECT p.produkt, p.sekcja, COUNT(pw.id) as ile_palet, COALESCE(SUM(pw.waga), 0) as suma_wagi
    FROM plan_produkcji p
    LEFT JOIN palety_workowanie pw ON p.id = pw.plan_id
    WHERE DATE(p.data_planu)=%s AND p.is_deleted=0
    GROUP BY p.id, p.produkt, p.sekcja
    ORDER BY p.sekcja, p.produkt
''', (today,))

plany = cursor.fetchall()

print('\nDETALE PALETEK PO PRODUKTACH:')
for p in plany:
    print(f'  {p["sekcja"]:12} | {p["produkt"]:20} | Palety: {p["ile_palet"]:2} szt | Waga: {p["suma_wagi"]:8.0f} kg')

# ===== PODSUMOWANIE =====
print(f'\n{"="*100}')
print('✅ OPERACJA KOMPLEKSOWA ZAKOŃCZONA')
print(f'{"="*100}')
print(f'Skopiowano palet do Workowania: {total_palety_copied}')
print(f'Zaktualizowano tonaz_rzeczywisty: {total_updated} planów')
print(f'{"="*100}\n')

cursor.close()
conn.close()
