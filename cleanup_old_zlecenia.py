#!/usr/bin/env python3
"""Permanently delete old zlecenia (orders) from bufor and plan_produkcji"""
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("\n=== USUWANIE STARYCH ZLECEŃ Z BUFORA ===\n")

# Get old entries to delete (older than today, not Testowy)
cursor.execute("""
    SELECT b.id, b.zasyp_id, b.produkt, b.data_planu
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
    WHERE b.status = 'aktywny'
    AND b.data_planu < CURDATE()
    AND b.produkt NOT IN ('Testowy2', 'Testowy4', 'Testowy1', 'Testowy3')
    ORDER BY b.data_planu ASC
""")

old_entries = cursor.fetchall()
print(f"📋 Found {len(old_entries)} old entries:")
for buf_id, z_id, produkt, data in old_entries:
    print(f"  - Bufor ID={buf_id}, Zasyp ID={z_id}, {produkt}, {data}")

if not old_entries:
    print("  ✅ Brak starych zleceń do usunięcia")
    cursor.close()
    conn.close()
    exit(0)

print("\n🔄 Usuwanie...")

# Collect Zasyp IDs and their Workowanie pairs
zasyp_ids_to_delete = []
workowanie_ids_to_delete = []

for buf_id, z_id, produkt, data in old_entries:
    if z_id:
        zasyp_ids_to_delete.append(z_id)
        
        # Find corresponding Workowanie plan
        cursor.execute("""
            SELECT id FROM plan_produkcji 
            WHERE sekcja='Workowanie' AND produkt=%s AND data_planu=%s
        """, (produkt, data))
        w_plan = cursor.fetchone()
        if w_plan:
            workowanie_ids_to_delete.append(w_plan[0])

# 1. Delete from bufor
cursor.execute("""
    DELETE FROM bufor WHERE data_planu < CURDATE() 
    AND produkt NOT IN ('Testowy2', 'Testowy4', 'Testowy1', 'Testowy3')
    AND status = 'aktywny'
""")
bufor_deleted = cursor.rowcount
print(f"  ✓ Usunięto {bufor_deleted} wpisów z tabeli bufor")

# 2. Delete palety_workowanie for old Workowanie plans
if workowanie_ids_to_delete:
    placeholders = ','.join(['%s'] * len(workowanie_ids_to_delete))
    cursor.execute(f"""
        DELETE FROM palety_workowanie WHERE plan_id IN ({placeholders})
    """, workowanie_ids_to_delete)
    palety_deleted = cursor.rowcount
    print(f"  ✓ Usunięto {palety_deleted} palet z palety_workowanie")

# 3. Delete Workowanie plans
if workowanie_ids_to_delete:
    placeholders = ','.join(['%s'] * len(workowanie_ids_to_delete))
    cursor.execute(f"""
        DELETE FROM plan_produkcji WHERE id IN ({placeholders})
    """, workowanie_ids_to_delete)
    workowanie_deleted = cursor.rowcount
    print(f"  ✓ Usunięto {workowanie_deleted} planów z Workowanie")

# 4. Delete Zasyp plans
if zasyp_ids_to_delete:
    placeholders = ','.join(['%s'] * len(zasyp_ids_to_delete))
    cursor.execute(f"""
        DELETE FROM plan_produkcji WHERE id IN ({placeholders})
    """, zasyp_ids_to_delete)
    zasyp_deleted = cursor.rowcount
    print(f"  ✓ Usunięto {zasyp_deleted} planów z Zasyp")

conn.commit()

print("\n✅ KOMPLETNE USUNIĘCIE:")
print(f"  - Bufor entries: {bufor_deleted}")
print(f"  - Palety: {palety_deleted if workowanie_ids_to_delete else 0}")
print(f"  - Workowanie plans: {workowanie_deleted if workowanie_ids_to_delete else 0}")
print(f"  - Zasyp plans: {zasyp_deleted if zasyp_ids_to_delete else 0}")

# Verify
cursor.execute("""
    SELECT COUNT(*) FROM bufor WHERE status='aktywny'
""")
remaining = cursor.fetchone()[0]
print(f"\n📊 Pozostało w bufor: {remaining} wpisów")

cursor.close()
conn.close()
