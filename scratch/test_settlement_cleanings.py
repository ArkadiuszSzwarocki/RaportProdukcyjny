import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection
from app.blueprints.planista.panel_data import load_primary_plan_rows, build_panel_summary_context, load_agro_plan_rows

def test():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        wybrana_data = '2026-05-22'
        print("PSD Cleanings:")
        plany_list = load_primary_plan_rows(cursor, wybrana_data, 'PSD')
        for p in plany_list:
            if p['sekcja'].lower() == 'czyszczenie':
                print("Found PSD cleaning:", p)
        
        print("\nAGRO Cleanings:")
        plany_agro = load_agro_plan_rows(cursor, wybrana_data)
        for p in plany_agro:
            if p['sekcja'].lower() == 'czyszczenie':
                print("Found AGRO cleaning:", p)
                
        ctx = build_panel_summary_context(
            cursor, wybrana_data, 'psd', 'PSD', 'plan_produkcji',
            plany_list, plany_agro, 0, 0, 0, 0, 0
        )
        print("\nPSD Settlement rozliczenia:")
        for r in ctx['rozliczenia']:
            if r['produkt'].lower() == 'czyszczenie':
                print("PSD settlement row:", r)

        ctx_agro = build_panel_summary_context(
            cursor, wybrana_data, 'agro', 'AGRO', 'plan_produkcji_agro',
            plany_list, plany_agro, 0, 0, 0, 0, 0
        )
        print("\nAGRO Settlement rozliczenia:")
        for r in ctx_agro['rozliczenia']:
            if r['produkt'].lower() == 'czyszczenie':
                print("AGRO settlement row:", r)
    finally:
        conn.close()

if __name__ == '__main__':
    test()
