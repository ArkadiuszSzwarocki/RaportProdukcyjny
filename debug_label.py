import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from flask import Flask
from app.db import get_db_connection
import datetime

def test_label():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # We don't know paleta_id, let's just get the last one from magazyn_palety
        cursor.execute("SELECT id FROM magazyn_palety ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            print("No palettes found")
            return
        paleta_id = row[0]
        print(f"Testing paleta_id = {paleta_id}")
        
        cursor.execute('''
            SELECT mp.plan_id, mp.waga_netto, p.produkt 
            FROM magazyn_palety mp
            JOIN plan_produkcji p ON mp.plan_id = p.id
            WHERE mp.id = %s
        ''', (paleta_id,))
        row = cursor.fetchone()
        
        if row:
            plan_id, paleta_waga, produkt = row
            cursor.execute('''
                SELECT COALESCE(SUM(waga_netto), 0) 
                FROM magazyn_palety 
                WHERE plan_id = %s AND id <= %s
            ''', (plan_id, paleta_id))
            cumulative_paleta_waga = cursor.fetchone()[0]
        else:
            print("Fallback")
            return

        cursor.execute('SELECT zasyp_id FROM plan_produkcji WHERE id = %s', (plan_id,))
        zasyp_check = cursor.fetchone()
        if zasyp_check and zasyp_check[0]:
            zasyp_plan_id = zasyp_check[0]
        else:
            zasyp_plan_id = plan_id

        cursor.execute('''
            SELECT id, waga, nr_szarzy
            FROM szarze 
            WHERE plan_id = %s 
            ORDER BY data_dodania ASC, id ASC
        ''', (zasyp_plan_id,))
        szarze_rows = cursor.fetchall()
        
        szarza_nr = 1
        cumulative_szarza = 0
        for i, s_row in enumerate(szarze_rows):
            cumulative_szarza += s_row[1]
            szarza_nr = s_row[2] if s_row[2] is not None else (i + 1)
            if cumulative_szarza >= cumulative_paleta_waga:
                break
                
        if not szarze_rows:
            szarza_nr = "?"
            
        data_wydruku = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        print(f"Success! plan_id={zasyp_plan_id}, szarza_nr={szarza_nr}, waga={paleta_waga}")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_label()
