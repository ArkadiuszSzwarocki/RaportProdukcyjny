#!/usr/bin/env python3
"""Napraw Plan 897 - ustaw zasyp_id = 896"""
import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("="*80)
print("NAPRAWIAM: Plan 897 <- zasyp_id = 896")
print("="*80)

# Pokaż stan przed
cursor.execute("""
    SELECT id, sekcja, zasyp_id, status, tonaz FROM plan_produkcji WHERE id IN (896, 897)
""")

print("\nStan PRZED:")
for row in cursor.fetchall():
    id, sekcja, zasyp_id, status, tonaz = row
    print(f"  Plan {id}: sekcja={sekcja}, zasyp_id={zasyp_id}, status={status}, tonaz={tonaz}")

# Ustaw zasyp_id dla Plan 897
cursor.execute("""
    UPDATE plan_produkcji SET zasyp_id = 896 WHERE id = 897
""")
print(f"\n✓ Updated {cursor.rowcount} row(s)")
conn.commit()

# Pokaż stan po
cursor.execute("""
    SELECT id, sekcja, zasyp_id, status, tonaz FROM plan_produkcji WHERE id IN (896, 897)
""")

print("\nStan PO NAPRAWIE:")
for row in cursor.fetchall():
    id, sekcja, zasyp_id, status, tonaz = row
    print(f"  Plan {id}: sekcja={sekcja}, zasyp_id={zasyp_id}, status={status}, tonaz={tonaz}")

# Sprawdź czy teraz 896 powinno wpaść do bufora
print("\n" + "="*80)
print("TEST: Czy Plan 896 spełnia warunki do bufora?")
print("="*80)

cursor.execute("""
    SELECT 
        z.id,
        z.status as zasyp_status,
        z.tonaz_rzeczywisty,
        w.id as workowanie_id,
        w.status as workowanie_status,
        (w.status IN ('w toku', 'zaplanowane') AND z.status IN ('w toku', 'zakonczone') AND z.tonaz_rzeczywisty > 0) as should_be_in_buffer
    FROM plan_produkcji z
    LEFT JOIN plan_produkcji w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
    WHERE z.id = 896 AND z.sekcja = 'Zasyp'
""")

row = cursor.fetchone()
if row:
    zid, z_status, tonaz, w_id, w_status, should_be = row
    print(f"\nZasyp {zid}:")
    print(f"  Status: {z_status} ✓" if z_status in ('w toku', 'zakonczone') else f"  Status: {z_status} ✗")
    print(f"  Tonaz_rzeczywisty: {tonaz} kg ✓" if tonaz and tonaz > 0 else f"  Tonaz_rzeczywisty: {tonaz} ✗")
    print(f"  Powiązane Workowanie: {w_id} (status={w_status}) ✓" if w_id else "  Powiązane Workowanie: BRAK ✗")
    print(f"  Workowanie status: {w_status} ✓" if w_status in ('w toku', 'zaplanowane') else f"  Workowanie status: {w_status} ✗")
    
    if should_be:
        print(f"\n✅ Plan 896 POWINNO być w buforze (wszystkie warunki spełnione)")
    else:
        print(f"\n❌ Plan 896 NIE POWINNO być w buforze")
else:
    print("Plan nie znaleziony!")

# Uruchom refresh_bufor_queue aby dodać do bufora
print("\n" + "="*80)
print("Odświeżanie bufora...")
print("="*80)

from app.db import refresh_bufor_queue
refresh_bufor_queue(conn)

# Sprawdź czy jest w buforze
cursor.execute("""
    SELECT id, status, tonaz_rzeczywisty, kolejka FROM bufor WHERE zasyp_id = 896
""")

buf_rows = cursor.fetchall()
print(f"\nWpisy w buforze dla Zasyp 896:")
if buf_rows:
    for buf_id, buf_status, buf_tonaz, buf_kolejka in buf_rows:
        print(f"  ✓ Bufor ID {buf_id}: status={buf_status}, tonaz={buf_tonaz}, kolejka={buf_kolejka}")
else:
    print("  BRAK - wpisy wymazane przez refresh_bufor_queue")

conn.commit()
conn.close()

print("\n" + "="*80)
print("GOTOWE!")
print("="*80)
