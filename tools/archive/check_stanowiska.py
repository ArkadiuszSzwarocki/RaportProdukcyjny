#!/usr/bin/env python3
"""
Narzędzie do sprawdzania stanu stanowisk produkcyjnych.
Pokazuje palety aktualnie znajdujące się na linii (bufor workowania).
"""
import sys
from datetime import date
sys.path.insert(0, '.')

from app.db import get_db_connection, get_table_name
from tabulate import tabulate


def sprawdz_stanowisko(linia='AGRO'):
    """Sprawdź co znajduje się na stanowisku produkcyjnym dla danej linii."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    table_pal = get_table_name('palety_workowanie', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    
    print(f"\n{'='*80}")
    print(f"🏭 STAN STANOWISKA PRODUKCYJNEGO - Linia: {linia}")
    print(f"{'='*80}\n")
    
    # Pobierz palety z bufora workowania (jeszcze nieprzyjęte do magazynu)
    cursor.execute(f"""
        SELECT 
            pw.id as paleta_id,
            pw.nr_palety as sscc,
            p.id as plan_id,
            p.produkt,
            pw.waga as waga_kg,
            pw.data_dodania as czas_dodania,
            COALESCE(pw.status, 'bufor') as status,
            pw.dodal_login as operator,
            p.status as status_zlecenia
        FROM {table_pal} pw
        JOIN {table_plan} p ON pw.plan_id = p.id
        WHERE DATE(p.data) = %s
        ORDER BY pw.data_dodania DESC
    """, (date.today(),))
    
    palety = cursor.fetchall()
    
    if not palety:
        print(f"✅ Brak palet na stanowisku - wszystko przyjęte do magazynu")
    else:
        # Grupuj po zleceniach
        zlecenia = {}
        for pal in palety:
            plan_id = pal[2]
            if plan_id not in zlecenia:
                zlecenia[plan_id] = {
                    'produkt': pal[3],
                    'status_zlecenia': pal[8],
                    'palety': []
                }
            zlecenia[plan_id]['palety'].append({
                'id': pal[0],
                'sscc': pal[1],
                'waga': pal[4],
                'czas': pal[5],
                'status': pal[6],
                'operator': pal[7] or '-'
            })
        
        # Wyświetl każde zlecenie z paletami
        for plan_id, dane in zlecenia.items():
            print(f"📋 Zlecenie #{plan_id}: {dane['produkt']} ({dane['status_zlecenia']})")
            print(f"   Palety na stanowisku: {len(dane['palety'])} szt.\n")
            
            tabela = []
            for p in dane['palety']:
                tabela.append([
                    p['id'],
                    p['sscc'] or '-',
                    f"{p['waga']:.0f} kg",
                    p['czas'].strftime('%H:%M:%S') if hasattr(p['czas'], 'strftime') else str(p['czas']),
                    p['status'],
                    p['operator']
                ])
            
            print(tabulate(
                tabela,
                headers=['ID', 'SSCC', 'Waga', 'Dodano', 'Status', 'Operator'],
                tablefmt='simple'
            ))
            print()
    
    # Podsumowanie
    cursor.execute(f"""
        SELECT 
            COUNT(*) as ilosc_palet,
            SUM(pw.waga) as suma_waga,
            COUNT(DISTINCT pw.plan_id) as ilosc_zlecen
        FROM {table_pal} pw
        JOIN {table_plan} p ON pw.plan_id = p.id
        WHERE DATE(p.data) = %s
    """, (date.today(),))
    
    suma = cursor.fetchone()
    if suma and suma[0] > 0:
        print(f"\n{'='*80}")
        print(f"📊 PODSUMOWANIE:")
        print(f"   • Palet na stanowisku: {suma[0]} szt.")
        print(f"   • Łączna waga: {suma[1]:.0f} kg")
        print(f"   • Aktywne zlecenia: {suma[2]}")
        print(f"{'='*80}\n")
    
    cursor.close()
    conn.close()


if __name__ == '__main__':
    # Możesz podać linię jako argument: python tools/check_stanowiska.py AGRO
    linia = sys.argv[1] if len(sys.argv) > 1 else 'AGRO'
    linia = linia.upper()
    
    if linia not in ['AGRO', 'PSD']:
        print(f"❌ Nieznana linia: {linia}. Użyj: AGRO lub PSD")
        sys.exit(1)
    
    sprawdz_stanowisko(linia)
