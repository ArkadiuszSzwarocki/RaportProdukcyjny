#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Przenosi surowiec między zbiornikami produkcyjnymi.
Transfer: ACP Kwaśna z BB18 → BB15
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name


def transfer_zbiornik(ruch_id, stary_zbiornik, nowy_zbiornik, linia='Agro', dry_run=True):
    """Przenosi surowiec między zbiornikami."""
    table_ruch = get_table_name('magazyn_ruch', linia)
    table_surowce = get_table_name('magazyn_surowce', linia)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Sprawdź czy ruch istnieje
        cursor.execute(
            f"SELECT r.id, r.zbiornik, r.ilosc, r.typ_ruchu, r.status, r.autor_login, r.autor_data, "
            f"COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa_surowca "
            f"FROM {table_ruch} r "
            f"LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id "
            f"WHERE r.id = %s",
            (ruch_id,)
        )
        ruch = cursor.fetchone()
        
        if not ruch:
            print(f"❌ Nie znaleziono ruchu o ID {ruch_id}")
            return False
        
        print(f"\n{'='*80}")
        print(f"TRANSFER ZBIORNIKA - {'DRY RUN (symulacja)' if dry_run else 'WYKONANIE'}")
        print(f"{'='*80}\n")
        
        print(f"📋 Szczegóły ruchu:")
        print(f"   ID ruchu:        {ruch['id']}")
        print(f"   Surowiec:        {ruch['nazwa_surowca']}")
        print(f"   Ilość:           {abs(float(ruch['ilosc'] or 0)):.1f} kg")
        print(f"   Typ ruchu:       {ruch['typ_ruchu']}")
        print(f"   Status:          {ruch['status']}")
        print(f"   Autor:           {ruch['autor_login']}")
        print(f"   Data:            {ruch['autor_data']}")
        print(f"\n🔄 Transfer:")
        print(f"   Stary zbiornik:  {ruch['zbiornik']} → {stary_zbiornik} (oczekiwany)")
        print(f"   Nowy zbiornik:   {nowy_zbiornik}")
        
        # Sprawdź czy zbiornik się zgadza
        if ruch['zbiornik'].upper() != stary_zbiornik.upper():
            print(f"\n⚠️  OSTRZEŻENIE: Zbiornik w bazie ({ruch['zbiornik']}) różni się od oczekiwanego ({stary_zbiornik})")
            print(f"   Czy kontynuować? (aktualny: {ruch['zbiornik']} → nowy: {nowy_zbiornik})")
        
        if dry_run:
            print(f"\n{'='*80}")
            print("✅ DRY RUN - NIE WYKONANO ŻADNYCH ZMIAN")
            print(f"{'='*80}")
            print("\nAby wykonać transfer, uruchom ponownie bez flagi --dry-run")
            return True
        
        # Wykonaj update
        stary_komentarz = ruch.get('komentarz') or ''
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        nowy_komentarz = f"[TRANSFER {timestamp}: {ruch['zbiornik']} → {nowy_zbiornik}] {stary_komentarz}".strip()
        
        cursor.execute(
            f"UPDATE {table_ruch} SET zbiornik = %s, komentarz = %s WHERE id = %s",
            (nowy_zbiornik.upper(), nowy_komentarz, ruch_id)
        )
        
        # Log do palety_historia jeśli mamy surowiec_id
        if ruch.get('surowiec_id'):
            cursor.execute(
                "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) "
                "VALUES (%s, %s, 'surowiec', 'TRANSFER', %s, 'system')",
                (ruch['surowiec_id'], linia, f"Transfer zbiornika: {ruch['zbiornik']} → {nowy_zbiornik}")
            )
        
        conn.commit()
        
        print(f"\n{'='*80}")
        print("✅ TRANSFER WYKONANY POMYŚLNIE")
        print(f"{'='*80}")
        print(f"\nSurowiec {ruch['nazwa_surowca']} został przeniesiony:")
        print(f"  {ruch['zbiornik']} → {nowy_zbiornik}")
        print(f"\nMożesz sprawdzić wynik na: /agro/magazyn/surowce-w-produkcji")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ BŁĄD: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Transfer surowca między zbiornikami')
    parser.add_argument('--ruch-id', type=int, default=236, help='ID ruchu do modyfikacji (domyślnie: 236)')
    parser.add_argument('--stary-zbiornik', default='BB18', help='Stary zbiornik (domyślnie: BB18)')
    parser.add_argument('--nowy-zbiornik', default='BB15', help='Nowy zbiornik (domyślnie: BB15)')
    parser.add_argument('--linia', default='Agro', help='Linia produkcyjna (domyślnie: Agro)')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Symulacja bez zmian (domyślnie: włączone)')
    parser.add_argument('--execute', action='store_true', help='Wykonaj zmiany (wyłącz dry-run)')
    
    args = parser.parse_args()
    
    # Jeśli użytkownik podał --execute, wyłącz dry-run
    dry_run = not args.execute
    
    print("\n" + "="*80)
    print("TRANSFER SUROWCA MIĘDZY ZBIORNIKAMI")
    print("="*80)
    print(f"\nParametry:")
    print(f"  Ruch ID:         {args.ruch_id}")
    print(f"  Stary zbiornik:  {args.stary_zbiornik}")
    print(f"  Nowy zbiornik:   {args.nowy_zbiornik}")
    print(f"  Linia:           {args.linia}")
    print(f"  Tryb:            {'DRY RUN (symulacja)' if dry_run else 'WYKONANIE'}")
    
    if dry_run:
        print("\n⚠️  DRY RUN: Żadne zmiany NIE zostaną zapisane w bazie danych")
        print("   Aby wykonać transfer, dodaj flagę --execute")
    else:
        print("\n⚠️  WYKONANIE: Zmiany ZOSTANĄ ZAPISANE w bazie danych!")
        odpowiedz = input("\nCzy na pewno chcesz kontynuować? (tak/nie): ")
        if odpowiedz.lower() not in ['tak', 't', 'yes', 'y']:
            print("\n❌ Anulowano przez użytkownika")
            sys.exit(0)
    
    success = transfer_zbiornik(
        ruch_id=args.ruch_id,
        stary_zbiornik=args.stary_zbiornik,
        nowy_zbiornik=args.nowy_zbiornik,
        linia=args.linia,
        dry_run=dry_run
    )
    
    sys.exit(0 if success else 1)
