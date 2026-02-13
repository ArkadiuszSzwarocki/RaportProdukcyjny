#!/usr/bin/env python3
"""Diagnose czy szarża z zakoniczonego Zasypu wpadają do bufora"""
import mysql.connector
from app.config import DB_CONFIG
from datetime import date, timedelta

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("="*80)
print("DIAGNOZA: Czy szarża z Zasypu trafia do bufora?")
print("="*80)

# 1. Pokaż logikę w refresh_bufor_queue - jakie warunki muszą być spełnione
print("\n📋 LOGIKA BUFORA (jakie szarże powinny trafiać do bufora):")
print("-" * 80)
print("✓ Szarża z Zasypu trafia do bufora jeśli:")
print("  1. Zasyp ma STATUS = 'w toku' LUB 'zakonczone'")
print("  2. Zasyp ma odpowiadające Workowanie")
print("  3. Workowanie ma STATUS = 'w toku' LUB 'zaplanowane'")
print("  4. Zasyp.tonaz_rzeczywisty > 0")
print()

# 2. Pobierz wszystkie kombinacje Zasyp+Workowanie
print("2️⃣ SPRAWDZENIE: Zasypy z odpowiadającymi Workowaniami")
print("-" * 80)

today = str(date.today())
yesterday = str(date.today() - timedelta(days=1))

cursor.execute("""
    SELECT 
        z.id as zasyp_id,
        z.status as zasyp_status,
        z.tonaz_rzeczywisty,
        z.produkt,
        w.id as workowanie_id,
        w.status as workowanie_status,
        b.id as bufor_id,
        b.status as bufor_status
    FROM plan_produkcji z
    LEFT JOIN plan_produkcji w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
    LEFT JOIN bufor b ON b.zasyp_id = z.id
    WHERE z.sekcja = 'Zasyp'
      AND z.data_planu IN (%s, %s)
    ORDER BY z.data_planu DESC, z.id
""", (today, yesterday))

rows = cursor.fetchall()
print(f"Znaleziono {len(rows)} Zasypy z ostatnich 2 dni\n")

should_be_in_buffer = []
not_in_buffer = []

for zasyp_id, z_status, tonaz_rz, produkt, w_id, w_status, b_id, b_status in rows:
    # Sprawdź czy powinien być w buforze
    should_be = (
        w_id is not None  # ma Workowanie
        and w_status in ('w toku', 'zaplanowane')  # Workowanie ma prawidłowy status
        and z_status in ('w toku', 'zakonczone')  # Zasyp ma prawidłowy status
        and tonaz_rz and tonaz_rz > 0  # ma tonaz_rzeczywisty > 0
    )
    
    is_in_buffer = b_id is not None and b_status == 'aktywny'
    
    status_icon = "✓" if should_be and is_in_buffer else "✗" if should_be and not is_in_buffer else "⊘"
    
    info = {
        'zasyp_id': zasyp_id,
        'produkt': produkt,
        'zasyp_status': z_status,
        'workowanie_id': w_id,
        'workowanie_status': w_status,
        'tonaz': tonaz_rz,
        'bufor_id': b_id,
        'bufor_status': b_status,
        'should_be': should_be,
        'is_in_buffer': is_in_buffer
    }
    
    if should_be:
        should_be_in_buffer.append(info)
        if not is_in_buffer:
            not_in_buffer.append(info)
    
    w_status_str = f"{w_status:12s}" if w_id else "BRAK        "
    tonaz_str = f"{tonaz_rz:7.0f}" if tonaz_rz else "      0"
    b_status_str = f"{b_status:12s}" if b_id else "BRAK        "
    
    print(f"{status_icon} Zasyp {zasyp_id:4d} ({produkt:15s}) | Zasyp={z_status:12s} | "
          f"Workowanie={w_status_str} | Tonaz={tonaz_str} kg | "
          f"Bufor={b_status_str}")

print(f"\n📊 PODSUMOWANIE:")
print(f"  - Szarż które POWINNE być w buforze: {len(should_be_in_buffer)}")
print(f"  - Szarż które SĄ w buforze: {len([x for x in should_be_in_buffer if x['is_in_buffer']])}")
print(f"  - Szarż które POWINNE być ale NIE SĄ: {len(not_in_buffer)}")

if not_in_buffer:
    print(f"\n⚠️  PROBLEMY (szarże które nie wpadły do bufora):")
    print("-" * 80)
    for info in not_in_buffer:
        print(f"Zasyp {info['zasyp_id']:4d} ({info['produkt']}) - tonaz={info['tonaz']:.0f} kg")
        print(f"  ├─ Zasyp status: {info['zasyp_status']}")
        print(f"  ├─ Workowanie ID {info['workowanie_id']} status: {info['workowanie_status']}")
        print(f"  └─ Powinne być w buforze: {info['should_be']} | Jest: {info['is_in_buffer']}")
else:
    print(f"\n✅ Wszystkie szarże które powinne być w buforze - SĄ w buforze!")

# 3. Sprawdź czy refresh_bufor_queue dodaje nowe wpisy
print("\n\n3️⃣ TEST: Czy refresh_bufor_queue dodaje wpisy do bufora?")
print("-" * 80)

from app.db import refresh_bufor_queue

print("Uruchamianie refresh_bufor_queue()...")
refresh_bufor_queue(conn)
print("✓ refresh_bufor_queue() completed\n")

# Re-check po refresh
cursor.execute("""
    SELECT COUNT(*) FROM bufor 
    WHERE status = 'aktywny' 
    AND data_planu IN (%s, %s)
""", (today, yesterday))

count = cursor.fetchone()[0]
print(f"Wpisy w buforze po refresh: {count}")

conn.close()

print("\n" + "="*80)
print("WNIOSEK:")
print("="*80)
if not not_in_buffer:
    print("✅ KOD DZIAŁA PRAWIDŁOWO - szarże z zakoniczonego Zasypu wpadają do bufora")
    print("   Logika jest poprawna, można ją zostawić.")
else:
    print("❌ PROBLEM - nie wszystkie szarże wpadają do bufora")
    print("   Sprawdź czy:")
    print("   - Workowanie ma prawidłowy status (w toku/zaplanowane)")
    print("   - Łańcuch FK zasyp_id w Workowanie jest prawidłowy")
    print("   - Zasyp ma tonaz_rzeczywisty > 0")

print("="*80)
