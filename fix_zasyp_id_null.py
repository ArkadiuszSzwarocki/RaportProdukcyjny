#!/usr/bin/env python3
"""Fix: Napraw zasyp_id w Workowaniu"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection
from datetime import date

dzisiaj = date.today()

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*80)
print("🔧 FIX: Naprawianie zasyp_id w Workowaniu")
print("="*80)

# Znajdź Workowania z zasyp_id=NULL które mają odpowiadające Zasypy
print(f"\n1️⃣  Szukanie Workowania z zasyp_id=NULL...")
cursor.execute("""
    SELECT w.id, w.produkt, w.data_planu
    FROM plan_produkcji w
    WHERE w.sekcja = 'Workowanie'
    AND w.zasyp_id IS NULL
    AND w.status IN ('zaplanowane', 'w toku')
    AND DATE(w.data_planu) = %s
""", (dzisiaj,))

bad_work = cursor.fetchall()
print(f"   Znaleziono: {len(bad_work)}")

for w_id, w_prod, w_data in bad_work:
    print(f"\n   🔍 Workowanie ID {w_id}: {w_prod} ({w_data})")
    
    # Znajdź odpowiadający Zasyp po produkcie i dacie
    cursor.execute("""
        SELECT id, tonaz, tonaz_rzeczywisty, status
        FROM plan_produkcji
        WHERE sekcja = 'Zasyp'
        AND produkt = %s
        AND DATE(data_planu) = %s
        ORDER BY status DESC
        LIMIT 1
    """, (w_prod, w_data))
    
    zasyp = cursor.fetchone()
    if zasyp:
        z_id, z_tonaz, z_tonaz_rz, z_status = zasyp
        print(f"      ✅ Znaleziono Zasyp ID {z_id}: {w_prod} tonaz={z_tonaz} rzecz={z_tonaz_rz} status={z_status}")
        
        # Napraw FK
        cursor.execute("""
            UPDATE plan_produkcji
            SET zasyp_id = %s
            WHERE id = %s
        """, (z_id, w_id))
        
        print(f"      ✏️  Ustawiono: Workowanie(ID={w_id}).zasyp_id = {z_id}")
    else:
        print(f"      ❌ Nie znaleziono Zasypu dla produktu '{w_prod}' w dniu {w_data}")

conn.commit()

# Teraz odśwież bufor
print(f"\n2️⃣  Odświeżam bufor...")
from app.db import refresh_bufor_queue
try:
    refresh_bufor_queue(conn)
    print("   ✅ Bufor odświeżony")
except Exception as e:
    print(f"   ❌ Błąd: {e}")

conn.close()
print("\n" + "="*80)
print("✅ GOTOWE! Teraz spróbuj start_zlecenie na Workowaniu\n")
