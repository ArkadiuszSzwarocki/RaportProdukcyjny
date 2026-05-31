import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection

def fix_scc_codes():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = '''
            SELECT w.id as wpis_id, w.nr_palety, w.paleta_id, w.linia 
            FROM magazyn_inwentaryzacja_wpisy w
            WHERE w.typ_palety IN ('wyrób gotowy', 'wyrob gotowy')
              AND w.nr_palety IS NOT NULL 
              AND w.paleta_id IS NOT NULL 
              AND w.stan_przed IS NULL
              AND DATE(w.data_wprowadzenia) = CURDATE()
        '''
        cursor.execute(query)
        wpisy = cursor.fetchall()
        
        print(f"Znaleziono {len(wpisy)} nowych palet wyrobu gotowego z dzisiaj.")
        
        updated_count = 0
        for w in wpisy:
            linia = w['linia'] or 'PSD'
            table = 'magazyn_palety' if linia.upper() == 'PSD' else f"magazyn_palety_{linia.lower()}"
            cursor.execute(f"UPDATE {table} SET nr_palety = %s WHERE id = %s", (w['nr_palety'], w['paleta_id']))
            if cursor.rowcount > 0:
                updated_count += 1
                print(f"Zaktualizowano {table} ID {w['paleta_id']} -> nr_palety: {w['nr_palety']}")
        
        conn.commit()
        print(f"Pomyślnie zaktualizowano {updated_count} wpisów.")
    except Exception as e:
        print(f"Wystąpił błąd: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

fix_scc_codes()
