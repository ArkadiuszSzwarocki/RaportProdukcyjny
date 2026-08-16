import os
import sys

# Ustawienie ścieżek
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.utils.db import get_db_connection

app = create_app()

def fix_scc_codes():
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # Znajdź wpisy inwentaryzacyjne dodane dzisiaj jako "nowe" dla wyrobów gotowych
            query = """
                SELECT w.id as wpis_id, w.nr_palety, w.paleta_id, w.linia 
                FROM magazyn_inwentaryzacja_wpisy w
                JOIN magazyn_inwentaryzacja_sesje s ON w.sesja_id = s.id
                WHERE w.typ_palety IN ('wyrób gotowy', 'wyrob gotowy')
                  AND w.nr_palety IS NOT NULL 
                  AND w.paleta_id IS NOT NULL 
                  AND w.stan_przed IS NULL
                  AND DATE(w.data_wprowadzenia) = CURDATE()
            """
            cursor.execute(query)
            wpisy = cursor.fetchall()
            
            print(f"Znaleziono {len(wpisy)} nowych palet wyrobu gotowego z dzisiaj.")
            
            updated_count = 0
            for w in wpisy:
                # Wybierz odpowiednią tabelę
                linia = w['linia'] or 'PSD'
                table = f"magazyn_palety" if linia.upper() == 'PSD' else f"magazyn_palety_{linia.lower()}"
                
                # Aktualizuj nr_palety w tabeli magazyn_palety
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

if __name__ == '__main__':
    fix_scc_codes()
