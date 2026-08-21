#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnoza i naprawa numeracji szarż AGRO
"""
import sys
from datetime import datetime, date
sys.path.insert(0, '.')

from app.db import get_db_connection

def diagnose_szarze():
    """Sprawdź aktualny stan szarż AGRO z dzisiaj"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Sprawdź szarże z dzisiaj
        today = date.today()
        cursor.execute("""
            SELECT 
                s.id as szarza_id,
                s.nr_szarzy,
                s.plan_id,
                s.waga,
                s.godzina,
                s.data_dodania,
                p.produkt,
                p.nazwa_zlecenia,
                p.data_planu,
                p.sekcja
            FROM szarze_agro s
            JOIN plan_produkcji_agro p ON s.plan_id = p.id
            WHERE p.data_planu = %s
            ORDER BY s.nr_szarzy ASC
        """, (today,))
        
        szarze = cursor.fetchall()
        
        if not szarze:
            print(f"❌ Brak szarż AGRO z dzisiaj ({today})")
            return None
            
        print(f"\n📊 Szarże AGRO z dnia {today}:")
        print("=" * 100)
        
        plan_id = None
        last_nr = 0
        missing = []
        
        for s in szarze:
            print(f"Szarża #{s['nr_szarzy']:2d} | ID: {s['szarza_id']:3d} | Plan: {s['plan_id']:3d} | "
                  f"Waga: {s['waga']:7.1f} kg | Godz: {s['godzina']} | "
                  f"Produkt: {s['produkt']} ({s['nazwa_zlecenia'] or 'brak nazwy'})")
            
            plan_id = s['plan_id']
            
            # Sprawdź luki w numeracji
            if s['nr_szarzy'] > last_nr + 1:
                for missing_nr in range(last_nr + 1, s['nr_szarzy']):
                    missing.append(missing_nr)
            last_nr = s['nr_szarzy']
        
        print("=" * 100)
        
        if missing:
            print(f"\n⚠️  BRAKUJĄCE NUMERY: {missing}")
        else:
            print("\n✅ Numeracja ciągła, brak luk")
        
        # Sprawdź dosypki
        cursor.execute("""
            SELECT 
                d.id,
                d.szarza_id,
                d.nazwa,
                d.kg,
                d.data_zlecenia,
                d.potwierdzone,
                d.anulowana
            FROM dosypki_agro d
            WHERE d.plan_id = %s
            ORDER BY d.data_zlecenia ASC
        """, (plan_id,))
        
        dosypki = cursor.fetchall()
        if dosypki:
            print(f"\n📦 Dosypki dla planu {plan_id}:")
            print("=" * 100)
            for d in dosypki:
                status = "✓" if d['potwierdzone'] else "⏳"
                if d['anulowana']:
                    status = "✗"
                szarza_info = f"→ Szarża #{d['szarza_id']}" if d['szarza_id'] else "→ Ogólna"
                print(f"{status} Dosypka #{d['id']:3d} | {d['nazwa']:20s} | {d['kg']:6.1f} kg | "
                      f"{d['data_zlecenia']} {szarza_info}")
            print("=" * 100)
        
        return {
            'szarze': szarze,
            'plan_id': plan_id,
            'missing': missing,
            'last_nr': last_nr,
            'dosypki': dosypki
        }
        
    finally:
        conn.close()


def add_szarza_7(plan_id, waga=1000.0, godzina=None):
    """Dodaj szarżę #7"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Pobierz info o planie
        cursor.execute("""
            SELECT produkt, typ_produkcji, data_planu 
            FROM plan_produkcji_agro 
            WHERE id = %s
        """, (plan_id,))
        
        plan = cursor.fetchone()
        if not plan:
            print(f"❌ Nie znaleziono planu {plan_id}")
            return False
        
        # Jeśli nie podano godziny, użyj aktualnej
        if godzina is None:
            godzina = datetime.now().strftime('%H:%M:%S')
        
        # Sprawdź czy szarża #7 już istnieje
        cursor.execute("""
            SELECT id FROM szarze_agro 
            WHERE plan_id = %s AND nr_szarzy = 7
        """, (plan_id,))
        
        if cursor.fetchone():
            print(f"⚠️  Szarża #7 już istnieje dla planu {plan_id}")
            return False
        
        # Dodaj szarżę #7
        now = datetime.now()
        cursor.execute("""
            INSERT INTO szarze_agro (
                plan_id, nr_szarzy, waga, godzina, data_dodania,
                produkt, typ_produkcji, data_planu
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            plan_id,
            7,
            waga,
            godzina,
            now,
            plan['produkt'],
            plan['typ_produkcji'],
            plan['data_planu']
        ))
        
        szarza_id = cursor.lastrowid
        
        # Zaktualizuj tonaz_rzeczywisty
        cursor.execute("""
            UPDATE plan_produkcji_agro 
            SET tonaz_rzeczywisty = (
                SELECT COALESCE(SUM(waga), 0) 
                FROM szarze_agro 
                WHERE plan_id = %s
            ) + (
                SELECT COALESCE(SUM(kg), 0) 
                FROM dosypki_agro 
                WHERE plan_id = %s 
                  AND potwierdzone = 1 
                  AND COALESCE(anulowana, 0) = 0
            )
            WHERE id = %s
        """, (plan_id, plan_id, plan_id))
        
        conn.commit()
        
        print(f"\n✅ Dodano szarżę #7 (ID: {szarza_id}) dla planu {plan_id}")
        print(f"   Waga: {waga} kg, Godzina: {godzina}, Produkt: {plan['produkt']}")
        
        return szarza_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Błąd dodawania szarży: {e}")
        return False
    finally:
        conn.close()


def add_dosypka_hydro(plan_id, szarza_id, kg=25.0, godzina=None):
    """Dodaj dosypkę 25 kg hydro do szarży #7"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Jeśli nie podano godziny, użyj aktualnej
        if godzina is None:
            godzina = datetime.now().strftime('%H:%M:%S')
        
        now = datetime.now()
        data_zlecenia = now
        
        # Dodaj dosypkę
        cursor.execute("""
            INSERT INTO dosypki_agro (
                plan_id, szarza_id, nazwa, kg, 
                data_zlecenia, potwierdzone, anulowana
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            plan_id,
            szarza_id,
            'Hydro',
            kg,
            data_zlecenia,
            1,  # potwierdzone
            0   # nie anulowana
        ))
        
        dosypka_id = cursor.lastrowid
        
        # Zaktualizuj tonaz_rzeczywisty (dodaj dosypkę)
        cursor.execute("""
            UPDATE plan_produkcji_agro 
            SET tonaz_rzeczywisty = (
                SELECT COALESCE(SUM(waga), 0) 
                FROM szarze_agro 
                WHERE plan_id = %s
            ) + (
                SELECT COALESCE(SUM(kg), 0) 
                FROM dosypki_agro 
                WHERE plan_id = %s 
                  AND potwierdzone = 1 
                  AND COALESCE(anulowana, 0) = 0
            )
            WHERE id = %s
        """, (plan_id, plan_id, plan_id))
        
        conn.commit()
        
        print(f"\n✅ Dodano dosypkę Hydro (ID: {dosypka_id}) dla szarży #{szarza_id}")
        print(f"   Waga: {kg} kg, Godzina: {godzina}")
        
        return dosypka_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Błąd dodawania dosypki: {e}")
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    print("\n🔍 DIAGNOZA SZARŻ AGRO")
    print("=" * 100)
    
    result = diagnose_szarze()
    
    if result:
        plan_id = result['plan_id']
        missing = result['missing']
        
        if 6 in missing or 7 not in [s['nr_szarzy'] for s in result['szarze']]:
            print(f"\n💡 Wykryto brak szarży #7")
            
            # Sprawdź ostatnią godzinę aby się wpasować
            last_time = None
            last_nr = 0
            for s in result['szarze']:
                if s['godzina']:
                    last_time = s['godzina']
                    last_nr = s['nr_szarzy']
            
            print(f"\n📝 Proponowana akcja:")
            print(f"   Plan ID: {plan_id}")
            print(f"   Ostatnia szarża: #{last_nr} o {last_time}")
            print(f"   Dodać szarżę #7 z dosypką 25 kg Hydro")
            
            response = input(f"\n❓ Dodać szarżę #7 z wagą 1000 kg i dosypką 25 kg Hydro? (tak/nie): ")
            
            if response.lower() in ['tak', 't', 'yes', 'y']:
                # Dodaj szarżę #7
                szarza_id = add_szarza_7(plan_id, waga=1000.0)
                
                if szarza_id:
                    # Dodaj dosypkę
                    add_dosypka_hydro(plan_id, szarza_id, kg=25.0)
                    
                    print("\n" + "=" * 100)
                    print("✅ GOTOWE! Uruchom ponownie diagnostykę aby sprawdzić:")
                    print(f"   python {__file__}")
            else:
                print("\n❌ Anulowano")
    
    print("\n" + "=" * 100)
