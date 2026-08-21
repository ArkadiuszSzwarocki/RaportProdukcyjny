#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdza status zbiornika BB01 w bazie danych.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db

def check_bb01():
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    print("=" * 60)
    print("SPRAWDZANIE ZBIORNIKA BB01")
    print("=" * 60)
    
    # 1. Sprawdź magazyn_ruch
    print("\n1. MAGAZYN_RUCH (wszystkie wpisy dla BB01):")
    cursor.execute("""
        SELECT 
            mr.id,
            mr.surowiec_id,
            ms.nazwa as surowiec_nazwa,
            mr.typ_ruchu,
            mr.ilosc,
            mr.ilosc_po,
            mr.zbiornik,
            mr.autor_login,
            mr.autor_data
        FROM magazyn_ruch mr
        LEFT JOIN magazyn_surowce ms ON ms.id = mr.surowiec_id
        WHERE mr.zbiornik = 'BB01'
        ORDER BY mr.autor_data DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  ID: {row['id']}, Surowiec: {row['surowiec_nazwa']}, Typ: {row['typ_ruchu']}, "
                  f"Ilosc: {row['ilosc']}, Po: {row['ilosc_po']}, Data: {row['autor_data']}")
    else:
        print("  Brak wpisów dla BB01")
    
    # 2. Sprawdź aktualny stan z magazyn_surowce
    print("\n2. MAGAZYN_SUROWCE (palety w BB01):")
    cursor.execute("""
        SELECT 
            id,
            nr_palety,
            nazwa,
            stan_magazynowy,
            lokalizacja,
            linia,
            created_at,
            updated_at
        FROM magazyn_surowce
        WHERE linia = 'BB01'
        ORDER BY updated_at DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  ID: {row['id']}, Nr: {row['nr_palety']}, Nazwa: {row['nazwa']}, "
                  f"Stan: {row['stan_magazynowy']}, Lok: {row['lokalizacja']}, Linia: {row['linia']}")
    else:
        print("  Brak palet z linia='BB01'")
    
    # 3. Sprawdź zagregowany stan systemowy
    print("\n3. ZAGREGOWANY STAN (suma kg na BB01):")
    cursor.execute("""
        SELECT 
            zbiornik,
            SUM(ilosc_po) as stan_systemowy,
            COUNT(*) as liczba_ruchow
        FROM magazyn_ruch
        WHERE zbiornik = 'BB01'
        GROUP BY zbiornik
    """)
    row = cursor.fetchone()
    if row:
        print(f"  Zbiornik: {row['zbiornik']}, Stan: {row['stan_systemowy']} kg, Ruchów: {row['liczba_ruchow']}")
    else:
        print("  Brak danych zagregowanych")
    
    # 4. Sprawdź ostatni ruch
    print("\n4. OSTATNI RUCH NA BB01:")
    cursor.execute("""
        SELECT 
            mr.typ_ruchu,
            mr.ilosc,
            mr.ilosc_po,
            ms.nazwa as surowiec_nazwa,
            mr.autor_login,
            mr.autor_data
        FROM magazyn_ruch mr
        LEFT JOIN magazyn_surowce ms ON ms.id = mr.surowiec_id
        WHERE mr.zbiornik = 'BB01'
        ORDER BY mr.autor_data DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        print(f"  Typ: {row['typ_ruchu']}, Surowiec: {row['surowiec_nazwa']}, "
              f"Ilosc: {row['ilosc']}, Po: {row['ilosc_po']}, Data: {row['autor_data']}")
    else:
        print("  Brak ostatniego ruchu")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 60)

if __name__ == '__main__':
    check_bb01()
