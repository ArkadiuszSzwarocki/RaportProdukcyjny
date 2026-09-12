from flask import jsonify, request, session
from app.db import get_db_connection, get_table_name

class PalletDeleteController:
    @staticmethod
    def delete_pallet():
        """Permanently delete duplicate or test pallets from database (requires admin role)."""
        role = (session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()
        if role not in ('masteradmin', 'admin', 'administrator'):
            return jsonify({'success': False, 'error': 'Brak uprawnień. Wymagana rola admin.'}), 403

        data = request.get_json() or {}
        pallet_id = data.get('id')
        pallet_type = data.get('type')
        linia = data.get('linia', 'PSD')

        if not all([pallet_id, pallet_type]):
            return jsonify({'success': False, 'error': 'Brak parametrów id lub type'}), 400

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            if pallet_type in ('Surowiec',):
                table = get_table_name('magazyn_surowce', linia)
                col_amount = 'stan_magazynowy'
                col_name = 'nazwa'
            elif pallet_type in ('Opakowanie',):
                table = get_table_name('magazyn_opakowania', linia)
                col_amount = 'stan_magazynowy'
                col_name = 'nazwa'
            else:
                table = get_table_name('magazyn_palety', linia)
                col_amount = 'waga_netto'
                col_name = 'produkt'

            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'error': f'Paleta ID {pallet_id} nie istnieje w tabeli {table}'}), 404

            # Archive before delete
            try:
                cursor.execute("""
                    INSERT INTO magazyn_archiwum (original_id, nr_palety, nazwa, typ_palety, linia, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row['id'], row.get('nr_palety'), row.get(col_name), pallet_type, linia,
                      row.get(col_amount, 0), row.get('lokalizacja'), session.get('login', 'admin'),
                      'USUNIĘTO: duplikat/paleta testowa'))
            except Exception as ae:
                print(f"Archive warning (non-fatal): {ae}")

            cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))
            
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, %s, 'USUNIECIE_TRWALE', %s, %s, %s)",
                    (pallet_id, linia, pallet_type.lower(), row.get('lokalizacja'), f"Trwałe usunięcie palety: {row.get('nr_palety', pallet_id)}, powód: duplikat/testowa", session.get('login', 'admin'))
                )
            except Exception as hist_err:
                print(f"History log warning: {hist_err}")
            
            conn.commit()
            return jsonify({'success': True, 'message': f'Paleta {row.get("nr_palety", pallet_id)} usunięta trwale.'})
        except Exception as e:
            conn.rollback()
            print(f"Error deleting pallet: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            conn.close()
