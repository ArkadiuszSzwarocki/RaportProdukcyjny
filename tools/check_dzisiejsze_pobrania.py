#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostyka dzisiejszych pobrań surowców na produkcję.
Sprawdza dlaczego przypisane zbiorniki nie są widoczne.
"""
import sys
import os
from datetime import datetime, date

# Dodaj katalog główny do PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name


def sprawdz_dzisiejsze_pobrania(linia='Agro'):
    """Sprawdza wszystkie dzisiejsze pobrania na produkcję i ich status."""
    table_ruch = get_table_name('magazyn_ruch', linia)
    table_surowce = get_table_name('magazyn_surowce', linia)
    
    dzis = date.today()
    
    print(f"\n{'='*80}")
    print(f"DIAGNOSTYKA DZISIEJSZYCH POBRAŃ - {dzis}")
    print(f"{'='*80}\n")
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz dzisiejsze ruchy typu PRODUKCJA
        query = f"""
            SELECT 
                r.id, 
                r.surowiec_id,
                COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa,
                s.lokalizacja,
                r.zbiornik,
                r.ilosc,
                r.status,
                r.autor_login,
                r.autor_data,
                r.plan_id,
                r.komentarz
            FROM {table_ruch} r
            LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id
            WHERE r.typ_ruchu = 'PRODUKCJA' 
              AND DATE(r.autor_data) = %s
            ORDER BY r.autor_data DESC
        """
        
        cursor.execute(query, (dzis,))
        pobrania = cursor.fetchall()
        
        if not pobrania:
            print(f"❌ Brak pobrań typu PRODUKCJA dla daty {dzis}")
            return
        
        print(f"✅ Znaleziono {len(pobrania)} pobrań dzisiaj:\n")
        
        # Sprawdź każde pobranie
        for i, p in enumerate(pobrania, 1):
            print(f"─── POBRANIE #{i} (ID: {p['id']}) ───")
            print(f"  📦 Surowiec:    {p['nazwa'] or 'BRAK NAZWY'}")
            print(f"  📍 Lokalizacja: {p['lokalizacja'] or 'BRAK'}")
            print(f"  🏭 Zbiornik:    {p['zbiornik'] or '❌ NIE PRZYPISANO'}")
            print(f"  ⚖️  Ilość:       {p['ilosc']} kg")
            print(f"  ✔️  Status:      {p['status']}")
            print(f"  👤 Autor:       {p['autor_login']}")
            print(f"  🕐 Data:        {p['autor_data']}")
            print(f"  📋 Plan ID:     {p['plan_id'] or 'BRAK'}")
            
            # Sprawdź zwroty i korekty dla tego pobrania
            query_zwroty = f"""
                SELECT 
                    SUM(CASE WHEN typ_ruchu = 'ZWROT' THEN ilosc ELSE 0 END) as zwroty,
                    SUM(CASE WHEN typ_ruchu = 'INWENTARYZACJA_PROD' THEN ilosc ELSE 0 END) as korekty
                FROM {table_ruch}
                WHERE ruch_zrodlowy_id = %s
            """
            cursor.execute(query_zwroty, (p['id'],))
            ruchy = cursor.fetchone()
            
            zwroty = float(ruchy['zwroty'] or 0) if ruchy else 0
            korekty = float(ruchy['korekty'] or 0) if ruchy else 0
            pobrana = abs(float(p['ilosc'] or 0))
            stan_systemowy = pobrana - zwroty + korekty
            
            print(f"  📊 Stan obliczony:")
            print(f"     • Pobrano:   {pobrana} kg")
            print(f"     • Zwrócono:  {zwroty} kg")
            print(f"     • Korekty:   {korekty} kg")
            print(f"     • Stan:      {stan_systemowy} kg")
            
            if stan_systemowy <= 0:
                print(f"  ⚠️  PRZYCZYNA: Stan systemowy <= 0 (całkowicie zużyty/zwrócony)")
            elif not p['zbiornik']:
                print(f"  ⚠️  PRZYCZYNA: Zbiornik nie został przypisany podczas pobrania")
            elif p['status'] != 'POTWIERDZONE':
                print(f"  ⚠️  PRZYCZYNA: Status nie jest POTWIERDZONE")
            else:
                print(f"  ✅ Pobranie powinno być widoczne w widoku zbiorników")
            
            print()
        
        # Podsumowanie przyczyn
        print(f"\n{'='*80}")
        print("PODSUMOWANIE PROBLEMÓW:")
        print(f"{'='*80}\n")
        
        bez_zbiornika = sum(1 for p in pobrania if not p['zbiornik'])
        calkowicie_zuzyte = 0
        
        for p in pobrania:
            cursor.execute(query_zwroty, (p['id'],))
            ruchy = cursor.fetchone()
            zwroty = float(ruchy['zwroty'] or 0) if ruchy else 0
            korekty = float(ruchy['korekty'] or 0) if ruchy else 0
            pobrana = abs(float(p['ilosc'] or 0))
            stan = pobrana - zwroty + korekty
            if stan <= 0:
                calkowicie_zuzyte += 1
        
        print(f"📊 Pobrania bez przypisanego zbiornika: {bez_zbiornika}/{len(pobrania)}")
        print(f"📊 Pobrania całkowicie zużyte (stan <= 0): {calkowicie_zuzyte}/{len(pobrania)}")
        print(f"📊 Pobrania widoczne w widoku: {len(pobrania) - bez_zbiornika - calkowicie_zuzyte}/{len(pobrania)}")
        
        if bez_zbiornika > 0:
            print(f"\n💡 ROZWIĄZANIE 1: Podczas pobrania należy ZAWSZE wybierać zbiornik docelowy")
            print(f"   (nie zostawiać domyślnej opcji '-- opcjonalnie: wybierz zbiornik --')")
        
        if calkowicie_zuzyte > 0:
            print(f"\n💡 ROZWIĄZANIE 2: Jeśli surowiec jest całkowicie zużyty, nie pojawi się w widoku")
            print(f"   (widok pokazuje tylko zbiorniki z aktualnym stanem > 0)")
        
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    linia = sys.argv[1] if len(sys.argv) > 1 else 'Agro'
    sprawdz_dzisiejsze_pobrania(linia)
