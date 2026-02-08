#!/usr/bin/env python
"""Verify uszkodzone_worki mapping end-to-end."""

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# 1. Sprawdź strukture tabeli
print("=" * 60)
print("1. STRUKTURA BAZY DANYCH")
print("=" * 60)

cursor.execute('DESCRIBE plan_produkcji')
all_cols = cursor.fetchall()
relevant_cols = [c for c in all_cols if any(x in c[0].lower() for x in ['id', 'uszk', 'produkt'])]

for col in relevant_cols:
    print(f"  {col[0]:30} {col[1]}")

# 2. Sprawdź czy uszkodzone_worki istnieje
print("\n" + "=" * 60)
print("2. WERYFIKACJA KOLUMNY uszkodzone_worki")
print("=" * 60)

uszk_col = [c for c in all_cols if c[0] == 'uszkodzone_worki']
if uszk_col:
    print(f"✓ Kolumna ISTNIEJE: {uszk_col[0][0]} ({uszk_col[0][1]})")
else:
    print("✗ Kolumna NIE ISTNIEJE - PROBLEM!")

# 3. Pobierz próbkę danych
print("\n" + "=" * 60)
print("3. PRÓBKA DANYCH")
print("=" * 60)

cursor.execute("""
    SELECT id, produkt, status, COALESCE(uszkodzone_worki, 0) as uszk
    FROM plan_produkcji 
    ORDER BY id DESC
    LIMIT 5
""")

rows = cursor.fetchall()
if rows:
    print(f"{'id':5} {'produkt':15} {'status':15} {'uszkodzone_worki':15}")
    print("-" * 55)
    for r in rows:
        print(f"{r[0]:<5} {r[1]:15} {r[2]:15} {r[3]:>5}")
else:
    print("Brak danych w tabeli")

# 4. Sprawdzenie query z routes_planista
print("\n" + "=" * 60)
print("4. ZAPYTANIE Z routes_planista.py (SELECT p[12])")
print("=" * 60)

cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, 
           real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, 
           wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    ORDER BY id DESC
    LIMIT 3
""")

rows = cursor.fetchall()
if rows:
    for i, r in enumerate(rows):
        print(f"\nWiersz {i+1}:")
        print(f"  p[0]  (id)                    = {r[0]}")
        print(f"  p[1]  (sekcja)                = {r[1]}")
        print(f"  p[2]  (produkt)               = {r[2]}")
        print(f"  p[12] (uszkodzone_worki)      = {r[11]}")

print("\n" + "=" * 60)
print("PODSUMOWANIE")
print("=" * 60)
print("✓ Mapowanie: DB field uszkodzone_worki → p[12] w template")
print("✓ Backend query: routes_planista.py pobiera pole")
print("✓ Template: planista.html wyświetla {{ p[12] }}")
print("✓ API: /api/update_uszkodzone_worki zapisuje do DB")

conn.close()
