from flask import current_app, jsonify, request, session

from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required


def register_api_plan_ops_routes(api_bp):
    @api_bp.route('/update_uszkodzone_worki', methods=['POST'])
    @login_required
    def update_uszkodzone_worki():
        """Aktualizuj ilość uszkodzonych worków dla planu."""
        try:
            data = request.get_json()
            plan_id = data.get('plan_id') or data.get('id')
            uszkodzone_worki = int(data.get('uszkodzone_worki', 0))
            linia = data.get('linia', 'PSD').upper()

            if not plan_id:
                return jsonify({'success': False, 'message': 'Brak plan_id'}), 400

            if uszkodzone_worki < 0:
                return jsonify({'success': False, 'message': 'Ilość nie może być ujemna'}), 400

            conn = get_db_connection()
            cursor = conn.cursor()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"SELECT id FROM {table_plan} WHERE id = %s", (plan_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'message': 'Zlecenie nie zostało znalezione'}), 404

            cursor.execute(
                f'UPDATE {table_plan} SET uszkodzone_worki = %s WHERE id = %s',
                (uszkodzone_worki, plan_id),
            )

            cursor.execute(
                'INSERT INTO plan_history (plan_id, action, changes, user_login, created_at) VALUES (%s, %s, %s, %s, NOW())',
                (plan_id, 'uszkodzone_worki_update', f'Uszkodzono: {uszkodzone_worki} worków ({linia})', session.get('login')),
            )
            conn.commit()
            conn.close()

            return jsonify(
                {
                    'success': True,
                    'message': f'Zaktualizowano: {uszkodzone_worki} uszkodzonych worków',
                    'uszkodzone_worki': uszkodzone_worki,
                    'plan_id': plan_id,
                }
            )
        except ValueError:
            return jsonify({'success': False, 'message': 'Nieprawidłowa liczba'}), 400
        except Exception as error:
            current_app.logger.exception('Error updating uszkodzone_worki: %s', error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/update_odrzuty_przesiewacz', methods=['POST'])
    @login_required
    def update_odrzuty_przesiewacz():
        """Aktualizuj ilość odrzutów na przesiewaczu dla planu."""
        try:
            data = request.get_json()
            plan_id = data.get('plan_id') or data.get('id')
            odrzuty = float(data.get('odrzuty_przesiewacz', 0))
            linia = data.get('linia', 'PSD').upper()

            if not plan_id:
                return jsonify({'success': False, 'message': 'Brak plan_id'}), 400

            if odrzuty < 0:
                return jsonify({'success': False, 'message': 'Ilość nie może być ujemna'}), 400

            conn = get_db_connection()
            cursor = conn.cursor()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"SELECT id FROM {table_plan} WHERE id = %s", (plan_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'message': 'Zlecenie nie zostało znalezione'}), 404

            cursor.execute(
                f'UPDATE {table_plan} SET odrzuty_przesiewacz = %s WHERE id = %s',
                (odrzuty, plan_id),
            )

            cursor.execute(
                'INSERT INTO plan_history (plan_id, action, changes, user_login, created_at) VALUES (%s, %s, %s, %s, NOW())',
                (plan_id, 'odrzuty_przesiewacz_update', f'Odrzuty przesiewacz: {odrzuty} kg ({linia})', session.get('login')),
            )
            conn.commit()
            conn.close()

            return jsonify(
                {
                    'success': True,
                    'message': 'Zaktualizowano ilość odrzutów',
                    'plan_id': plan_id,
                }
            )
        except ValueError:
            return jsonify({'success': False, 'message': 'Nieprawidłowa liczba'}), 400
        except Exception as error:
            current_app.logger.exception('Error updating odrzuty_przesiewacz: %s', error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/get_deleted_plans/<date>', methods=['GET'])
    @roles_required('planista', 'admin')
    def get_deleted_plans(date):
        """Pobierz usunięte soft-delete zlecenia na dany dzień."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            linia = request.args.get('linia', 'PSD')
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(
                f'SELECT id, produkt, tonaz, status, deleted_at FROM {table_plan} WHERE DATE(data_planu) = %s AND is_deleted = 1 ORDER BY deleted_at DESC',
                (date,),
            )
            deleted_plans = cursor.fetchall()
            conn.close()

            result = []
            for row in deleted_plans:
                result.append(
                    {
                        'id': row[0],
                        'produkt': row[1],
                        'tonaz': row[2],
                        'status': row[3],
                        'deleted_at': str(row[4]) if row[4] else None,
                    }
                )

            return jsonify({'success': True, 'plans': result}), 200
        except Exception as error:
            try:
                conn.close()
            except Exception:
                pass
            current_app.logger.exception('Failed to get deleted plans for %s', date)
            return jsonify({'success': False, 'message': str(error)}), 500