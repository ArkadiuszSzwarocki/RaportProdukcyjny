import sys
import os

# Ensure app is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.db import get_db_connection

def fix_erroneous_100010():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        nr_palety = 'SUR000001782725623044'
        updates = []

        # 1. Update palety_historia (komentarz has 100010.0)
        cursor.execute("""
            UPDATE palety_historia 
            SET komentarz = REPLACE(REPLACE(komentarz, '100010.0', '1000.0'), '100010', '1000')
            WHERE komentarz LIKE '%100010%'
        """)
        updates.append(f"palety_historia: {cursor.rowcount} rows updated")

        # 2. Get paleta_id
        cursor.execute("SELECT id FROM magazyn_surowce WHERE nr_palety = %s", (nr_palety,))
        paleta = cursor.fetchone()
        
        if paleta:
            pid = paleta[0]
            # Update magazyn_ruch
            cursor.execute("""
                UPDATE magazyn_ruch 
                SET ilosc_po = 1000.0, ilosc = 0.0
                WHERE surowiec_id = %s AND (ilosc_po = 100010 OR ilosc_po = 100010.0 OR ilosc = 99010.0)
            """, (pid,))
            updates.append(f"magazyn_ruch: {cursor.rowcount} rows updated")
            
            # Update magazyn_agro_ruch
            cursor.execute("""
                UPDATE magazyn_agro_ruch 
                SET ilosc_po = 1000.0, ilosc = 0.0
                WHERE surowiec_id = %s AND (ilosc_po = 100010 OR ilosc_po = 100010.0 OR ilosc = 99010.0)
            """, (pid,))
            updates.append(f"magazyn_agro_ruch: {cursor.rowcount} rows updated")

        # 3. Update magazyn_inwentaryzacja_wpisy
        cursor.execute("""
            UPDATE magazyn_inwentaryzacja_wpisy 
            SET waga_faktyczna = 1000.0 
            WHERE nr_palety = %s AND (waga_faktyczna = 100010 OR waga_faktyczna = 100010.0)
        """, (nr_palety,))
        updates.append(f"magazyn_inwentaryzacja_wpisy: {cursor.rowcount} rows updated")
        
        # 4. Fallback if pallet was not found by nr_palety but records exist
        cursor.execute("""
            UPDATE magazyn_ruch 
            SET ilosc_po = 1000.0, ilosc = 0.0
            WHERE ilosc_po = 100010 OR ilosc_po = 100010.0
        """)
        if cursor.rowcount > 0:
            updates.append(f"magazyn_ruch (fallback): {cursor.rowcount} rows updated")

        conn.commit()
        
        for msg in updates:
            print(msg)
            
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_erroneous_100010()
