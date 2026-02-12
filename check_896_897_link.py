#!/usr/bin/env python3
"""Sprawdź dokładnie co się dzieje z Pln 896 i 897"""
import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("="*80)
print("SZCZEGÓŁOWA ANALIZA: Plan 896 (ZASYP) i Plan 897 (WORKOWANIE)")
print("="*80)

# Pobierz Plan 896
cursor.execute("""
    SELECT id, sekcja, produkt, status, tonaz, tonaz_rzeczywisty, zasyp_id
    FROM plan_produkcji
    WHERE id = 896
""")
p896 = cursor.fetchone()

# Pobierz Plan 897
cursor.execute("""
    SELECT id, sekcja, produkt, status, tonaz, tonaz_rzeczywisty, zasyp_id
    FROM plan_produkcji
    WHERE id = 897
""")
p897 = cursor.fetchone()

print("\n1️⃣  PLAN 896 (Zasyp - Filling):")
print("-" * 80)
if p896:
    id, sekcja, produkt, status, tonaz, tonaz_rz, zasyp_id = p896
    print(f"ID: {id}")
    print(f"Sekcja: {sekcja}")
    print(f"Produkt: {produkt}")
    print(f"Status: {status}")
    print(f"Tonaz (plan): {tonaz} kg")
    print(f"Tonaz_rzeczywisty (rzeczywisty): {tonaz_rz} kg")
    print(f"Zasyp_id: {zasyp_id}")
else:
    print("Plan nie znaleziony")

print("\n2️⃣  PLAN 897 (Workowanie - Packaging):")
print("-" * 80)
if p897:
    id, sekcja, produkt, status, tonaz, tonaz_rz, zasyp_id = p897
    print(f"ID: {id}")
    print(f"Sekcja: {sekcja}")
    print(f"Produkt: {produkt}")
    print(f"Status: {status}")
    print(f"Tonaz (plan): {tonaz} kg")
    print(f"Tonaz_rzeczywisty (rzeczywisty): {tonaz_rz} kg")
    print(f"Zasyp_id (FK do 896?): {zasyp_id}")
    
    if zasyp_id == 896:
        print(f"✓ Plan 897 ma poprawne FK do Plan 896")
    else:
        print(f"✗ Plan 897 ma ZŁĄ ref - zasyp_id={zasyp_id} zamiast 896")
else:
    print("Plan nie znaleziony")

# Sprawdź Link między 896 i 897
print("\n3️⃣  POWIĄZANIE 896 ↔ 897:")
print("-" * 80)
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji
    WHERE zasyp_id = 896 AND sekcja = 'Workowanie'
""")
count = cursor.fetchone()[0]
print(f"Planów Workowanie z zasyp_id=896: {count}")

if count > 0:
    cursor.execute("""
        SELECT id, status, tonaz, tonaz_rzeczywisty 
        FROM plan_produkcji
        WHERE zasyp_id = 896 AND sekcja = 'Workowanie'
    """)
    for w_id, w_status, w_tonaz, w_tonaz_rz in cursor.fetchall():
        print(f"  - ID {w_id}: status={w_status}, tonaz={w_tonaz}, tonaz_rz={w_tonaz_rz}")

# Sprawdź czy 896 jest w buforze
print("\n4️⃣  CZY PLAN 896 (ZASYP) JEST W BUFORZE?")
print("-" * 80)
cursor.execute("""
    SELECT id, status, tonaz_rzeczywisty, kolejka
    FROM bufor
    WHERE zasyp_id = 896
""")
buf_rows = cursor.fetchall()
if buf_rows:
    for buf_id, buf_status, buf_tonaz, buf_kolejka in buf_rows:
        print(f"Takk! Wpis w buforze ID {buf_id}: status={buf_status}, tonaz={buf_tonaz}, kolejka={buf_kolejka}")
else:
    print("NIE - Plan 896 nie ma wpisu w buforze")

# Sprawdź logikę: czy powinien być w buforze?
print("\n5️⃣  CZY PLAN 896 POWINIEN BYĆ W BUFORZE?")
print("-" * 80)
print("Warunki aby zapatrz wpadła do bufora (refresh_bufor_queue):")
print("  1. Zasyp.sekcja = 'Zasyp' ✓ ", end="")
if p896 and p896[1] == 'Zasyp': print("(spełniony)")
else: print("(NIE)")

print("  2. Workowanie.sekcja = 'Workowanie' ", end="")
if p897 and p897[1] == 'Workowanie': print("✓ (spełniony)")
else: print("(NIE)")

print("  3. Workowanie.zasyp_id = Zasyp.id ", end="")
if p897 and p897[6] == 896: print("✓ (spełniony)")
else: print("(NIE)")

print("  4. Workowanie.status IN ('w toku', 'zaplanowane') ", end="")
if p897 and p897[3] in ('w toku', 'zaplanowane'): print(f"✓ (spełniony: {p897[3]})")
else: print(f"(NIE: {p897[3] if p897 else 'N/A'})")

print("  5. Zasyp.status IN ('w toku', 'zakonczone') ", end="")
if p896 and p896[3] in ('w toku', 'zakonczone'): print(f"✓ (spełniony: {p896[3]})")
else: print(f"(NIE: {p896[3] if p896 else 'N/A'})")

print("  6. Zasyp.tonaz_rzeczywisty > 0 ", end="")
if p896 and p896[5] and p896[5] > 0: print(f"✓ (spełniony: {p896[5]} kg)")
else: print(f"(NIE: {p896[5] if p896 else 'N/A'} kg)")

all_conds = (
    p896 and p896[1] == 'Zasyp' and
    p897 and p897[1] == 'Workowanie' and
    p897[6] == 896 and
    p897[3] in ('w toku', 'zaplanowane') and
    p896[3] in ('w toku', 'zakonczone') and
    p896[5] and p896[5] > 0
)

print("\n" + "="*80)
if all_conds:
    print("✅ WNIOSEK: Plan 896 POWINIEN być w buforze (wszystkie warunki spełnione)")
else:
    print("❌ WNIOSEK: Plan 896 NIE POWINIEN być w buforze (nie wszystkie warunki spełnione)")

print("="*80)

conn.close()
