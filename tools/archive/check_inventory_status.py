#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdza status inwentaryzacji produkcji i wpisy w magazyn_ruch.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db

def check_inventory():
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    print("=" * 80)
    print("SPRAWDZANIE INWENTARYZACJI PRODUKCJI")
    print("=" * 80)
    
    # 1. Ostatnie sesje inwentaryzacji
    print("\n1. OSTATNIE SESJE INWENTARYZACJI:")
    cursor.execute("""
        SELECT 
            id,
            linia,
            status,
            lokalizacja,
            created_by,
            created_at,
            closed_at
        FROM magazyn_inwentaryzacja_produkcji_sesje
        ORDER BY id DESC
        LIMIT 5
    """)
    sesje = cursor.fetchall()
    if sesje:
        for s in sesje:
            print(f"  Sesja #{s['id']}: {s['status']}, Linia: {s['linia']}, Lok: {s['lokalizacja']}, "
                  f"Utworzył: {s['created_by']}, Data: {s['created_at']}")
    else:
        print("  Brak sesji")
    
    # 2. Sprawdź ostatnią sesję - czy była zatwierdzona
    if sesje:
        last_sesja_id = sesje[0]['id']
        print(f"\n2. WPISY W OSTATNIEJ SESJI #{last_sesja_id}:")
        cursor.execute("""
            SELECT 
                id,
                zbiornik,
                surowiec_nazwa,
                waga_systemowa,
                waga_faktyczna,
                ruch_id,
                old_ruch_id,
                paleta_id,
                nr_palety
            FROM magazyn_inwentaryzacja_produkcji_wpisy
            WHERE sesja_id = %s
            ORDER BY zbiornik
        """, (last_sesja_id,))
        wpisy = cursor.fetchall()
        if wpisy:
            for w in wpisy:
                print(f"  Zbiornik: {w['zbiornik']}, Surowiec: {w['surowiec_nazwa']}, "
                      f"Sys: {w['waga_systemowa']}, Fakt: {w['waga_faktyczna']}, "
                      f"Ruch_id: {w['ruch_id']}, Paleta_id: {w['paleta_id']}")
        else:
            print("  Brak wpisów")
    
    # 3. Sprawdź magazyn_ruch - czy są wpisy PRODUKCJA
    print("\n3. WPISY PRODUKCJA W MAGAZYN_RUCH (ostatnie 20):")
    cursor.execute("""
        SELECT 
            id,
            surowiec_id,
            surowiec_nazwa,
            typ_ruchu,
            ilosc,
            ilosc_po,
            zbiornik,
            status,
            autor_login,
            autor_data,
            komentarz
        FROM magazyn_ruch
        WHERE typ_ruchu = 'PRODUKCJA'
        ORDER BY autor_data DESC
        LIMIT 20
    """)
    ruchy = cursor.fetchall()
    if ruchy:
        for r in ruchy:
            print(f"  ID: {r['id']}, Zbiornik: {r['zbiornik']}, Surowiec: {r['surowiec_nazwa']}, "
                  f"Ilosc: {r['ilosc']}, Po: {r['ilosc_po']}, Status: {r['status']}, "
                  f"Data: {r['autor_data']}")
    else:
        print("  Brak wpisów PRODUKCJA")
    
    # 4. Sprawdź stan systemowy dla BB01
    print("\n4. STAN SYSTEMOWY BB01 (z agregacji):")
    cursor.execute("""
        SELECT 
            r.zbiornik,
            r.surowiec_nazwa,
            ABS(r.ilosc) as ilosc_pobrana,
            COALESCE((SELECT SUM(z.ilosc) FROM magazyn_ruch z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as ilosc_zwrocona,
            COALESCE((SELECT SUM(k.ilosc) FROM magazyn_ruch k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as ilosc_korekta,
            r.ilosc_po
        FROM magazyn_ruch r
        WHERE r.typ_ruchu = 'PRODUKCJA' 
        AND r.status = 'POTWIERDZONE'
        AND UPPER(TRIM(COALESCE(r.zbiornik, ''))) = 'BB01'
        ORDER BY r.autor_data DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            pobrana = float(r['ilosc_pobrana'] or 0)
            zwrocona = float(r['ilosc_zwrocona'] or 0)
            korekta = float(r['ilosc_korekta'] or 0)
            stan = pobrana - zwrocona + korekta
            print(f"  Zbiornik: {r['zbiornik']}, Surowiec: {r['surowiec_nazwa']}, "
                  f"Pobrana: {pobrana}, Zwrócona: {zwrocona}, Korekta: {korekta}, "
                  f"Stan: {stan}, ilosc_po: {r['ilosc_po']}")
    else:
        print("  Brak danych dla BB01")
    
    # 5. Sprawdź wszystkie zbiorniki z PRODUKCJA
    print("\n5. WSZYSTKIE ZBIORNIKI Z PRODUKCJA (grupowanie):")
    cursor.execute("""
        SELECT 
            zbiornik,
            COUNT(*) as liczba_wpisow,
            SUM(ABS(ilosc)) as suma_pobranych
        FROM magazyn_ruch
        WHERE typ_ruchu = 'PRODUKCJA' 
        AND status = 'POTWIERDZONE'
        AND COALESCE(NULLIF(TRIM(zbiornik), ''), '') <> ''
        GROUP BY zbiornik
        ORDER BY zbiornik
    """)
    zbiorniki = cursor.fetchall()
    if zbiorniki:
        for z in zbiorniki:
            print(f"  {z['zbiornik']}: {z['liczba_wpisow']} wpisów, suma: {z['suma_pobranych']} kg")
    else:
        print("  Brak zbiorników z PRODUKCJA")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 80)

if __name__ == '__main__':
    check_inventory()
