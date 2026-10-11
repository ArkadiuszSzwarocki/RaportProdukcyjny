"""
Skrypt przywracania palety SUR000001789972723706 do strefy MP01.
Usuwa blokady, ustawia lokalizację MP01 i rejestruje wpis w historii ruchów.
"""
import sys
import os
from datetime import datetime

# Dodaj katalog główny projektu do PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection
from app.services.warehouse_history.movement_recorder import MovementRecorder

TARGET_PALLET_NR = 'SUR000001789972723706'
TARGET_LOCATION = 'MP01'


def restore_pallet():
    print(f"=== Rozpoczynam przywracanie palety {TARGET_PALLET_NR} do {TARGET_LOCATION} ===")
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        tables_to_check = [
            ('magazyn_surowce', 'Surowiec'),
            ('magazyn_palety', 'Wyrób Gotowy'),
            ('magazyn_palety_agro', 'Wyrób Gotowy AGRO'),
            ('magazyn_opakowania', 'Opakowanie'),
            ('magazyn_dodatki', 'Dodatek')
        ]

        found = False
        for table_name, pallet_type in tables_to_check:
            cursor.execute(f"SELECT * FROM {table_name} WHERE nr_palety = %s", (TARGET_PALLET_NR,))
            rows = cursor.fetchall()
            if not rows:
                continue

            for row in rows:
                found = True
                pallet_id = row['id']
                old_loc = row.get('lokalizacja') or 'BRAK'
                nazwa = row.get('nazwa') or row.get('produkt') or 'Nieznany'
                qty = row.get('stan_magazynowy') if 'stan_magazynowy' in row else row.get('waga_netto', 0)

                print(f"Znaleziono paletę w tabeli {table_name}:")
                print(f"  • ID: {pallet_id}")
                print(f"  • Produkt/Nazwa: {nazwa}")
                print(f"  • Ilość: {qty}")
                print(f"  • Obecna lokalizacja: {old_loc}")
                print(f"  • Blokada (is_blocked): {row.get('is_blocked')}")

                # Aktualizacja lokalizacji i zdjęcie ewentualnych blokad
                update_cols = ["lokalizacja = %s", "is_blocked = 0"]
                params = [TARGET_LOCATION]
                if 'is_loaded' in row:
                    update_cols.append("is_loaded = 0")
                params.append(pallet_id)

                sql_update = f"UPDATE {table_name} SET {', '.join(update_cols)} WHERE id = %s"
                cursor.execute(sql_update, tuple(params))
                print(f"  -> Zaktualizowano lokalizację na {TARGET_LOCATION} oraz zdjęto blokady (is_blocked=0).")

                # Zapis w historii palety
                try:
                    MovementRecorder.record_movement(
                        cursor=cursor,
                        paleta_id=pallet_id,
                        nr_palety=TARGET_PALLET_NR,
                        source=old_loc,
                        destination=TARGET_LOCATION,
                        akcja='PRZESUNIECIE',
                        user='System / Admin',
                        typ_palety=pallet_type,
                        linia='AGRO' if 'agro' in table_name or TARGET_LOCATION.startswith('MP') else 'PSD',
                        komentarz=f"Przywrócenie palety ze strefy {old_loc} na strefę {TARGET_LOCATION}"
                    )
                    print("  -> Zarejestrowano ruch w historii palety.")
                except Exception as hist_err:
                    print(f"  ! Ostrzeżenie przy zapisie historii: {hist_err}")

        if not found:
            print(f"Nie znaleziono palety o numerze {TARGET_PALLET_NR} w żadnej z tabel magazynowych!")
            return False

        conn.commit()
        print(f"\nSukces: Paleta {TARGET_PALLET_NR} została pomyślnie przywrócona na lokalizację {TARGET_LOCATION}.")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Błąd podczas przywracania palety: {e}")
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    restore_pallet()
