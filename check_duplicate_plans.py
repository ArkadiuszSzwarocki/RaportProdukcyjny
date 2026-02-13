#!/usr/bin/env python3
"""Check for duplicate plans on Workowanie - all products"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_db_connection
from datetime import date
from collections import Counter

conn = get_db_connection()
cursor = conn.cursor()

dzisiaj = str(date.today())

# Szukaj WSZYSTKICH planów na Workowanie dzisiaj
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, zasyp_id
    FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Workowanie'
    ORDER BY kolejnosc, id
""", (dzisiaj,))

plans = cursor.fetchall()
print(f"📋 Wszystkie plany na Workowanie ({dzisiaj}):")
print(f"Znaleziono {len(plans)} planów:")
print()

# Zlicz duplikaty
produkty = [p[2] for p in plans]
duplikaty = {p: c for p, c in Counter(produkty).items() if c > 1}

if plans:
    for i, (id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rz, zasyp_id) in enumerate(plans, 1):
        marker = "⚠️ DUPLIKAT" if duplikaty and produkt in duplikaty else ""
        print(f"{i}. Plan ID {id} {marker}")
        print(f"   - Produkt: {produkt}")
        print(f"   - Tonaz: {tonaz} kg")
        print(f"   - Status: {status}")
        print(f"   - Kolejnosc: {kolejnosc}")
        print(f"   - Zasyp ID: {zasyp_id}")
        
        # Pokaż powiązany Zasyp
        if zasyp_id:
            cursor.execute("""
                SELECT id, sekcja, produkt, tonaz, status
                FROM plan_produkcji
                WHERE id = %s
            """, (zasyp_id,))
            zasyp = cursor.fetchone()
            if zasyp:
                w_id, w_sekcja, w_produkt, w_tonaz, w_status = zasyp
                print(f"   → Powiązany Zasyp (ID {zasyp_id}): {w_produkt} {w_tonaz}kg status={w_status}")
        print()

    if duplikaty:
        print()
        print("❌ DUPLIKATY ZNALEZIONE:")
        for produkt, count in duplikaty.items():
            print(f"   - {produkt}: {count} plany")
            # Pokaż IDs duplikatów
            ids = [p for p in plans if p[2] == produkt]
            print(f"     IDs: {[p[0] for p in ids]}")
            print(f"     Zasyp IDs: {[p[9] for p in ids]}")
            print()
            print("   🔧 Rekomendacja: Usuń jeden z duplikatów (np. ID " + str(ids[-1][0]) + ")")
else:
    print("❌ Brak planów dla Workowanie dzisiaj")

conn.close()


