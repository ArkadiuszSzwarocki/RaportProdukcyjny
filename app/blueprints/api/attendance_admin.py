from flask import current_app, jsonify, request, session

from app.db import get_db_connection
from app.decorators import roles_required, masteradmin_required


def register_api_attendance_admin_routes(api_bp):
    @api_bp.route('/obecnosc/delete-by-date', methods=['POST'])
    @masteradmin_required
    def delete_obecnosc_by_date():
        """Delete all attendance entries for a date and employee, with session-based undo."""
        try:
            data = request.get_json()
            date_str = data.get('date')
            pid = data.get('pid')

            if not date_str or not pid:
                return jsonify({'success': False, 'message': 'Brakuje parametrów'}), 400

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                'SELECT id, pracownik_id, data_wpisu, typ, ilosc_godzin FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s',
                (pid, date_str),
            )
            deleted_entries = cursor.fetchall()

            cursor.execute(
                'SELECT id, pracownik_id, data_wpisu, sekcja FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s',
                (pid, date_str),
            )
            deleted_obsada = cursor.fetchall()

            if not deleted_entries:
                conn.close()
                return jsonify({'success': False, 'message': 'Brak wpisów na podaną datę'}), 404

            cursor.execute('DELETE FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s', (pid, date_str))
            cursor.execute('DELETE FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s', (pid, date_str))

            conn.commit()
            conn.close()

            session['deleted_obecnosc'] = {
                'date': date_str,
                'pid': pid,
                'entries': [
                    {
                        'id': entry['id'],
                        'pracownik_id': entry['pracownik_id'],
                        'data_wpisu': str(entry['data_wpisu']),
                        'typ': entry['typ'],
                        'ilosc_godzin': entry['ilosc_godzin'],
                    }
                    for entry in deleted_entries
                ],
                'obsada_entries': [
                    {
                        'pracownik_id': obsada['pracownik_id'],
                        'data_wpisu': str(obsada['data_wpisu']),
                        'sekcja': obsada['sekcja'],
                    }
                    for obsada in deleted_obsada
                ],
            }
            session.modified = True

            entry_types = ', '.join(entry['typ'] for entry in deleted_entries)
            current_app.logger.info(
                '[ADMIN] Deleted %s obecnosc entries AND %s obsada entries for date=%s, pid=%s, types=%s',
                len(deleted_entries),
                len(deleted_obsada),
                date_str,
                pid,
                entry_types,
            )

            return jsonify(
                {
                    'success': True,
                    'message': f'Usunięto {len(deleted_entries)} wpisów z dnia {date_str} ({entry_types}). Pracownik usunięty z listy obsady. Możesz cofnąć zmiany.',
                }
            )
        except Exception as error:
            current_app.logger.error('Error deleting obecnosc entries: %s', error)
            return jsonify({'success': False, 'message': 'Błąd przy usuwaniu wpisów'}), 500

    @api_bp.route('/obecnosc/<int:obecnosc_id>', methods=['DELETE'])
    @masteradmin_required
    def delete_obecnosc(obecnosc_id):
        """Delete a single attendance entry by ID, with session-based undo."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                'SELECT id, pracownik_id, data_wpisu, typ, ilosc_godzin FROM obecnosc WHERE id=%s',
                (obecnosc_id,),
            )
            deleted_entry = cursor.fetchone()

            if not deleted_entry:
                conn.close()
                return jsonify({'success': False, 'message': 'Wpis nie znaleziony'}), 404

            cursor.execute('DELETE FROM obecnosc WHERE id=%s', (obecnosc_id,))
            conn.commit()
            conn.close()

            session['deleted_obecnosc'] = {
                'id': deleted_entry['id'],
                'pracownik_id': deleted_entry['pracownik_id'],
                'data_wpisu': str(deleted_entry['data_wpisu']),
                'typ': deleted_entry['typ'],
                'ilosc_godzin': deleted_entry['ilosc_godzin'],
            }
            session.modified = True

            current_app.logger.info(
                '[ADMIN] Deleted obecnosc entry ID=%s, data=%s, typ=%s',
                obecnosc_id,
                deleted_entry['data_wpisu'],
                deleted_entry['typ'],
            )
            return jsonify(
                {
                    'success': True,
                    'message': f"Usunięto wpis z dnia {deleted_entry['data_wpisu']} (typ: {deleted_entry['typ']}). Możesz cofnąć zmiany.",
                }
            )
        except Exception as error:
            current_app.logger.error('Error deleting obecnosc entry: %s', error)
            return jsonify({'success': False, 'message': 'Błąd przy usuwaniu wpisu'}), 500

    @api_bp.route('/obecnosc/restore', methods=['POST'])
    @masteradmin_required
    def restore_ostatnia_usuniety():
        """Restore the last deleted attendance entry or batch of entries from session."""
        try:
            deleted = session.get('deleted_obecnosc')
            if not deleted:
                return jsonify({'success': False, 'message': 'Brak usuniętego wpisu do przywrócenia'}), 400

            conn = get_db_connection()
            cursor = conn.cursor()

            if 'entries' in deleted:
                for entry in deleted['entries']:
                    cursor.execute(
                        'INSERT INTO obecnosc (pracownik_id, data_wpisu, typ, ilosc_godzin) VALUES (%s, %s, %s, %s)',
                        (entry['pracownik_id'], entry['data_wpisu'], entry['typ'], entry['ilosc_godzin']),
                    )

                if 'obsada_entries' in deleted:
                    for obsada in deleted['obsada_entries']:
                        cursor.execute(
                            'INSERT INTO obsada_zmiany (pracownik_id, data_wpisu, sekcja) VALUES (%s, %s, %s)',
                            (obsada['pracownik_id'], obsada['data_wpisu'], obsada['sekcja']),
                        )

                conn.commit()
                restored_count = len(deleted['entries'])
                message = f"Przywrócono {restored_count} wpisów z dnia {deleted['date']}"
            else:
                cursor.execute(
                    'INSERT INTO obecnosc (pracownik_id, data_wpisu, typ, ilosc_godzin) VALUES (%s, %s, %s, %s)',
                    (deleted['pracownik_id'], deleted['data_wpisu'], deleted['typ'], deleted['ilosc_godzin']),
                )
                conn.commit()
                restored_count = 1
                message = f"Przywrócono wpis z dnia {deleted['data_wpisu']}"

            conn.close()
            session.pop('deleted_obecnosc', None)
            session.modified = True

            current_app.logger.info('[ADMIN] Restored %s obecnosc entries and obsada', restored_count)
            return jsonify({'success': True, 'message': message})
        except Exception as error:
            current_app.logger.error('Error restoring obecnosc entry: %s', error)
            return jsonify({'success': False, 'message': 'Błąd przy przywracaniu wpisu'}), 500