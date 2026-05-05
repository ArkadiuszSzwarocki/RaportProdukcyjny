import mysql.connector

from flask import current_app, jsonify, request

from app.db import get_db_connection, get_table_name
from app.decorators import login_required


def register_api_product_routes(api_bp):
    @api_bp.route('/produkty', methods=['GET'])
    def get_produkty():
        """Zwraca listę dostępnych produktów (public - dla UI dropdownów)."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT id, nazwa_produktu, nr_receptury, typ_produkcji
                FROM produkty_receptury
                ORDER BY nazwa_produktu ASC
                """
            )

            produkty = cursor.fetchall()
            cursor.close()
            conn.close()

            return jsonify({'success': True, 'produkty': produkty}), 200
        except Exception as error:
            current_app.logger.exception('Error fetching produkty: %s', error)
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @api_bp.route('/produkty', methods=['POST'])
    @login_required
    def add_produkt():
        """Dodaje nowy produkt do listy."""
        try:
            data = request.get_json() or {}
            nazwa = (data.get('nazwa_produktu') or '').strip()
            nr_receptury = (data.get('nr_receptury') or '').strip()
            typ_produkcji = (data.get('typ_produkcji') or 'worki_zgrzewane_25').strip()

            if not nazwa:
                return jsonify({'success': False, 'message': 'Nazwa produktu jest wymagana'}), 400

            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    INSERT INTO produkty_receptury (nazwa_produktu, nr_receptury, typ_produkcji)
                    VALUES (%s, %s, %s)
                    """,
                    (nazwa, nr_receptury, typ_produkcji),
                )

                conn.commit()
                product_id = cursor.lastrowid
                return jsonify({'success': True, 'message': f'Produkt "{nazwa}" dodany do listy', 'product_id': product_id}), 201
            except mysql.connector.errors.IntegrityError:
                return jsonify({'success': False, 'message': f'Produkt "{nazwa}" już istnieje na liście'}), 409
            finally:
                cursor.close()
                conn.close()
        except Exception as error:
            current_app.logger.exception('Error adding produkt: %s', error)
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @api_bp.route('/produkty/<int:product_id>', methods=['PUT'])
    @login_required
    def update_produkt(product_id):
        """Aktualizuje produkt."""
        try:
            data = request.get_json() or {}
            nazwa = (data.get('nazwa_produktu') or '').strip()
            nr_receptury = (data.get('nr_receptury') or '').strip()
            typ_produkcji = (data.get('typ_produkcji') or 'worki_zgrzewane_25').strip()

            if not nazwa:
                return jsonify({'success': False, 'message': 'Nazwa produktu jest wymagana'}), 400

            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    UPDATE produkty_receptury
                    SET nazwa_produktu=%s, nr_receptury=%s, typ_produkcji=%s
                    WHERE id=%s
                    """,
                    (nazwa, nr_receptury, typ_produkcji, product_id),
                )
                conn.commit()

                if cursor.rowcount == 0:
                    return jsonify({'success': False, 'message': 'Produkt nie znaleziony'}), 404

                return jsonify({'success': True, 'message': f'Produkt "{nazwa}" zaktualizowany'}), 200
            except mysql.connector.errors.IntegrityError:
                return jsonify({'success': False, 'message': f'Produkt "{nazwa}" już istnieje na liście'}), 409
            finally:
                cursor.close()
                conn.close()
        except Exception as error:
            current_app.logger.exception('Error updating produkt: %s', error)
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500

    @api_bp.route('/produkty/<int:product_id>', methods=['DELETE'])
    @login_required
    def delete_produkt(product_id):
        """Usuwa produkt z listy."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            table_plan_psd = get_table_name('plan_produkcji', 'PSD')
            table_plan_agro = get_table_name('plan_produkcji', 'Agro')

            cursor.execute(
                f"""
                SELECT (
                    SELECT COUNT(*) FROM {table_plan_psd}
                    WHERE produkt = (SELECT nazwa_produktu FROM produkty_receptury WHERE id=%s)
                ) + (
                    SELECT COUNT(*) FROM {table_plan_agro}
                    WHERE produkt = (SELECT nazwa_produktu FROM produkty_receptury WHERE id=%s)
                ) as total_count
                """,
                (product_id, product_id),
            )

            result = cursor.fetchone()
            if result and result[0] > 0:
                return jsonify({'success': False, 'message': 'Nie można usunąć produktu - jest używany w planach'}), 409

            cursor.execute('DELETE FROM produkty_receptury WHERE id=%s', (product_id,))
            conn.commit()

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Produkt nie znaleziony'}), 404

            return jsonify({'success': True, 'message': 'Produkt usunięty z listy'}), 200
        except Exception as error:
            current_app.logger.exception('Error deleting produkt: %s', error)
            return jsonify({'success': False, 'message': f'Błąd serwera: {str(error)}'}), 500
        finally:
            cursor.close()
            conn.close()