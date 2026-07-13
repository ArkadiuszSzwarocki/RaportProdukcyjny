#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'a:\\GitHub\\RaportProdukcyjny')

from app.db import get_db_connection
from app.core.database import get_table_name

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

# Check PRODUKCJA for surowiec_id 312 (after dispatch)
table_ruch = get_table_name('magazyn_ruch', 'AGRO')

print("=== SPRAWDZAM BAZĘ PO DISPATCH ===\n")

cur.execute(f"""
    SELECT id, surowiec_id, typ_ruchu, ilosc, zbiornik, status, autor_data
    FROM {table_ruch}
    WHERE surowiec_id = 312
    ORDER BY id DESC
    LIMIT 5
""")

rows = cur.fetchall()
print(f"Rekordy dla surowiec_id=312:")
for row in rows:
    print(f"  ID: {row['id']}, Typ: {row['typ_ruchu']}, Ilość: {row['ilosc']}, Zbiornik: {row['zbiornik']}, Status: {row['status']}")

# Check WHERE clause conditions
print("\n=== SPRAWDZAM WARUNKI WHERE Z API ===\n")

cur.execute(f"""
    SELECT id, surowiec_id, typ_ruchu, zbiornik, status,
           COALESCE(NULLIF(TRIM(zbiornik), ''), '') as zbiornik_trimmed,
           COALESCE(NULLIF(TRIM(zbiornik), ''), '') <> '' as zbiornik_not_empty
    FROM {table_ruch}
    WHERE surowiec_id = 312
    ORDER BY id DESC
    LIMIT 3
""")

rows = cur.fetchall()
print("Sprawdzenie warunku WHERE:")
for row in rows:
    print(f"  Typ: {row['typ_ruchu']}, Zbiornik: '{row['zbiornik']}' (trimmed: '{row['zbiornik_trimmed']}'), Not empty: {row['zbiornik_not_empty']}, Status: {row['status']}")

# Full check for production inventory query
print("\n=== PEŁNY WARUNEK NA PRODUKCJĘ ===\n")

cur.execute(f"""
    SELECT r.id, r.surowiec_id, r.typ_ruchu, r.zbiornik, r.status,
           r.typ_ruchu = 'PRODUKCJA' as typ_ok,
           r.status = 'POTWIERDZONE' as status_ok,
           COALESCE(NULLIF(TRIM(r.zbiornik), ''), '') <> '' as zbiornik_ok
    FROM {table_ruch} r
    WHERE r.surowiec_id = 312
    ORDER BY r.id DESC
    LIMIT 3
""")

rows = cur.fetchall()
print("Warunki production_inventory:")
for row in rows:
    all_ok = row['typ_ok'] and row['status_ok'] and row['zbiornik_ok']
    print(f"  Typ={row['typ_ok']}, Status={row['status_ok']}, Zbiornik={row['zbiornik_ok']} => PASS: {all_ok}")

cur.close()
conn.close()
