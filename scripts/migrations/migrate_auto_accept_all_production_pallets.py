import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from datetime import datetime
from app.core.database import get_db_connection

def sync_unconfirmed_pallets():
    databases = ['biblioteka', 'biblioteka_testowa']
    
    for db_name in databases:
        print(f"\n================ Processing Database: {db_name} ================")
        conn = get_db_connection()
        setattr(conn, 'database', db_name)
        cursor = conn.cursor(dictionary=True)
        
        # 1. Check PSD palety_workowanie
        cursor.execute("""
            SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.data_dodania, pw.status,
                   pw.dodal_login, pw.nr_palety, pw.nr_plomby, pw.nr_palety_lp,
                   pl.data_planu, pl.produkt, pl.data_produkcji
            FROM palety_workowanie pw
            LEFT JOIN plan_produkcji pl ON pw.plan_id = pl.id
            WHERE pw.status != 'przyjeta' OR pw.status IS NULL
        """)
        psd_pallets = cursor.fetchall()
        print(f"[{db_name}] Found {len(psd_pallets)} unconfirmed PSD pallets in palety_workowanie")
        
        for p in psd_pallets:
            nr_palety = p.get('nr_palety')
            pw_id = p.get('id')
            waga = p.get('waga') or 0
            prod_name = p.get('produkt') or 'Wyrób gotowy PSD'
            plan_date = p.get('data_planu')
            prod_date = p.get('data_produkcji') or p.get('data_dodania') or datetime.now()
            user = p.get('dodal_login') or 'system'
            plomba = p.get('nr_plomby')
            lp = p.get('nr_palety_lp')
            
            # Check if exists in magazyn_palety
            cursor.execute("SELECT id FROM magazyn_palety WHERE nr_palety = %s OR paleta_workowanie_id = %s", (nr_palety, pw_id))
            exists = cursor.fetchone()
            
            if not exists and nr_palety:
                cursor.execute("""
                    INSERT INTO magazyn_palety (
                        paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto,
                        waga_brutto, tara, user_login, data_produkcji, lokalizacja,
                        nr_palety, nr_plomby, linia, nr_palety_lp, data_potwierdzenia
                    ) VALUES (%s, %s, %s, %s, %s, %s, 25, %s, %s, 'MGW01', %s, %s, 'PSD', %s, NOW())
                """, (
                    pw_id, p.get('plan_id'), plan_date, prod_name, waga,
                    waga + 25, user, prod_date, nr_palety, plomba, lp
                ))
            
            cursor.execute("UPDATE palety_workowanie SET status='przyjeta', waga_potwierdzona=%s WHERE id=%s", (waga, pw_id))
            
        # 2. Check AGRO palety_agro
        cursor.execute("""
            SELECT pa.id, pa.plan_id, pa.waga, pa.tara, pa.data_dodania, pa.status,
                   pa.dodal_login, pa.nr_palety, pa.nr_plomby, pa.nr_palety_lp,
                   pl.data_planu, pl.produkt, pl.data_produkcji
            FROM palety_agro pa
            LEFT JOIN plan_produkcji_agro pl ON pa.plan_id = pl.id
            WHERE pa.status != 'przyjeta' OR pa.status IS NULL
        """)
        agro_pallets = cursor.fetchall()
        print(f"[{db_name}] Found {len(agro_pallets)} unconfirmed AGRO pallets in palety_agro")
        
        for p in agro_pallets:
            nr_palety = p.get('nr_palety')
            pa_id = p.get('id')
            waga = p.get('waga') or 0
            prod_name = p.get('produkt') or 'Wyrób gotowy AGRO'
            plan_date = p.get('data_planu')
            prod_date = p.get('data_produkcji') or p.get('data_dodania') or datetime.now()
            user = p.get('dodal_login') or 'system'
            plomba = p.get('nr_plomby')
            lp = p.get('nr_palety_lp')
            
            # Check if exists in magazyn_palety
            cursor.execute("SELECT id FROM magazyn_palety WHERE nr_palety = %s OR (paleta_workowanie_id = %s AND linia = 'AGRO')", (nr_palety, pa_id))
            exists = cursor.fetchone()
            
            if not exists and nr_palety:
                cursor.execute("""
                    INSERT INTO magazyn_palety (
                        paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto,
                        waga_brutto, tara, user_login, data_produkcji, lokalizacja,
                        nr_palety, nr_plomby, linia, nr_palety_lp, data_potwierdzenia
                    ) VALUES (%s, %s, %s, %s, %s, %s, 25, %s, %s, 'MGW02', %s, %s, 'AGRO', %s, NOW())
                """, (
                    pa_id, p.get('plan_id'), plan_date, prod_name, waga,
                    waga + 25, user, prod_date, nr_palety, plomba, lp
                ))
                
            cursor.execute("UPDATE palety_agro SET status='przyjeta', waga_potwierdzona=%s WHERE id=%s", (waga, pa_id))
            
        conn.commit()
        conn.close()
        print(f"[{db_name}] Finished migration successfully.")

if __name__ == '__main__':
    sync_unconfirmed_pallets()
