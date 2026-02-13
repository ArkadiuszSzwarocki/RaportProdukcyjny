#!/usr/bin/env python3
"""Diagnose: Sprawdzenie zle odpowiadających Zasyp <-> Bufor <-> Workowanie"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection
from datetime import date

dzisiaj = date.today()

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*80)
print(f"📊 DIAGNOZ: Zasyp -> Bufor -> Workowanie ({dzisiaj})")
print("="*80)

# 1. Wszystkie Zasypy w toku dzisiaj
print(f"\n1️⃣  ZASYP (status='w toku' na dzisiaj):")
cursor.execute("""
    SELECT id, produkt, tonaz, tonaz_rzeczywisty, status, real_start
    FROM plan_produkcji
    WHERE sekcja = 'Zasyp' AND data_planu = %s AND status = 'w toku'
    ORDER BY real_start ASC
""", (dzisiaj,))
zasypy = cursor.fetchall()
print(f"   Znaleziono: {len(zasypy)}")
for z_id, z_prod, z_tonaz, z_tonaz_rz, z_status, z_start in zasypy:
    print(f"   - ID {z_id}: {z_prod} (plan={z_tonaz}, rzecz={z_tonaz_rz}) status={z_status} start={z_start}")

# 2. Sprawdź ile z nich jest w buforze
print(f"\n2️⃣  BUFOR (na dzisiaj, status='aktywny'):")
cursor.execute("""
    SELECT id, zasyp_id, produkt, tonaz_rzeczywisty, spakowano, kolejka
    FROM bufor
    WHERE data_planu = %s AND status = 'aktywny'
    ORDER BY kolejka ASC
""", (dzisiaj,))
bufory = cursor.fetchall()
print(f"   Znaleziono: {len(bufory)}")
for buf_id, buf_zasyp_id, buf_prod, buf_tonaz, buf_spak, buf_kolejka in bufory:
    print(f"   - ID {buf_id}: Zasyp_ID {buf_zasyp_id} | {buf_prod} | plan={buf_tonaz}, spak={buf_spak} | kolejka={buf_kolejka}")

# 3. Porównaj: które Zasypy z pkt 1 NIE MA w buforze?
print(f"\n3️⃣  ZASYPY BEZ BUFORA (problem!):")
zasyp_ids = {z[0] for z in zasypy}
bufor_zasyp_ids = {b[1] for b in bufory}
missing = zasyp_ids - bufor_zasyp_ids
print(f"   Znaleziono: {len(missing)}")
for z_id in missing:
    z_data = next((z for z in zasypy if z[0] == z_id), None)
    if z_data:
        print(f"   - Zasyp ID {z_id}: {z_data[1]} (tonaz_rzeczywisty={z_data[3]})")

# 4. Workowanie w toku dzisiaj
print(f"\n4️⃣  WORKOWANIE (status='w toku' na dzisiaj):")
cursor.execute("""
    SELECT id, produkt, tonaz, zasyp_id, status, real_start
    FROM plan_produkcji
    WHERE sekcja = 'Workowanie' AND data_planu = %s AND status = 'w toko'
    ORDER BY real_start ASC
""", (dzisiaj,))
workowania = cursor.fetchall()
print(f"   Znaleziono: {len(workowania)}")
for w_id, w_prod, w_tonaz, w_zasyp_id, w_status, w_start in workowania:
    print(f"   - ID {w_id}: {w_prod} (zasyp_id={w_zasyp_id}) tonaz={w_tonaz} status={w_status} start={w_start}")

# 5. Sprawdź Foreign Key - które Workowania nie mają OK zasyp_id
print(f"\n5️⃣  WORKOWANIE ZE ZŁYMI FK (status='zaplanowane'|'w toku'):")
cursor.execute("""
    SELECT id, produkt, tonaz, zasyp_id, status
    FROM plan_produkcji
    WHERE sekcja = 'Workowanie' AND data_planu = %s 
    AND status IN ('zaplanowane', 'w toku')
    AND (zasyp_id IS NULL OR zasyp_id NOT IN (
        SELECT id FROM plan_produkcji WHERE sekcja = 'Zasyp'
    ))
    ORDER BY status, id
""", (dzisiaj,))
bad_fks = cursor.fetchall()
print(f"   Znaleziono: {len(bad_fks)}")
for w_id, w_prod, w_tonaz, w_zasyp, w_status in bad_fks:
    print(f"   - ID {w_id}: {w_prod} (zasyp_id={w_zasyp}) tonaz={w_tonaz} status={w_status} ⚠️")

# 6. Analiza refresh_bufor_queue - sprawdź czy są problemy w logice
print(f"\n6️⃣  ANALIZ refresh_bufor_queue (INNER JOIN na zasyp_id):")
cursor.execute("""
    SELECT z.id, z.produkt, z.status, w.id as w_id, w.status as w_status, b.id as buf_id
    FROM plan_produkcji z
    LEFT JOIN plan_produkcji w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
    LEFT JOIN bufor b ON b.zasyp_id = z.id AND b.status = 'aktywny'
    WHERE z.sekcja = 'Zasyp' AND z.data_planu = %s 
    AND z.status IN ('w toku', 'zakonczone')
    ORDER BY z.id
""", (dzisiaj,))
analiza = cursor.fetchall()
print(f"   Zasypy które POWINNY być w buforze (logika refresh_bufor_queue):")
for z_id, z_prod, z_status, w_id, w_status, b_id in analiza:
    w_ok = "✅" if w_id and w_status in ('w toku', 'zaplanowane') else "❌"
    b_ok = "✅" if b_id else "❌"
    print(f"   - Zasyp {z_id}: {z_prod} ({z_status}) | Work={w_ok}({w_id}/{w_status}) | Buf={b_ok}({b_id})")

conn.close()
print("\n" + "="*80)
