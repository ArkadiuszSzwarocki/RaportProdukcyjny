from flask import render_template, request

from app.db import get_db_connection
from app.decorators import dynamic_role_required, masteradmin_required


def register_admin_production_routes(admin_bp, *, load_roles):
    @admin_bp.route('/admin/ustawienia/produkcja')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_produkcja():
        """Modern Production Management Dashboard for Supervisors."""
        linia = request.args.get('linia') or 'PSD'

        from app.db import get_table_name

        table_plan = get_table_name('plan_produkcji', linia)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f'SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM {table_plan} ORDER BY data_planu DESC LIMIT 50'
        )
        zlecenia_rows = cursor.fetchall()

        class _Z:
            def __init__(self, row):
                self.id = row[0]
                self.data_planu = row[1]
                self.sekcja = row[2]
                self.produkt = row[3]
                self.tonaz = row[4]
                self.tonaz_rzeczywisty = row[5]
                self.status = row[6]

        zlecenia = [_Z(row) for row in zlecenia_rows]
        roles = load_roles(cursor)

        surowce = []
        if str(linia).upper() == 'AGRO':
            cursor.execute('SELECT id, nazwa FROM magazyn_agro_slownik_surowce ORDER BY nazwa ASC')
            surowce = [{'id': row[0], 'nazwa': row[1]} for row in cursor.fetchall()]

        conn.close()

        return render_template('ustawienia_produkcja.html', zlecenia=zlecenia, roles=roles, linia=linia, surowce=surowce)

    @admin_bp.route('/admin/api/agro-surowce/add', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_add_agro_surowiec():
        from flask import jsonify
        nazwa = request.form.get('nazwa', '').strip()
        if not nazwa:
            return jsonify({'success': False, 'message': 'Nazwa surowca nie może być pusta.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id FROM magazyn_agro_slownik_surowce WHERE LOWER(nazwa) = LOWER(%s)', (nazwa,))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'Taki surowiec już istnieje w słowniku.'}), 400

            cursor.execute('INSERT INTO magazyn_agro_slownik_surowce (nazwa) VALUES (%s)', (nazwa,))
            conn.commit()
            return jsonify({'success': True, 'message': f'Surowiec "{nazwa}" został dodany do bazy.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Błąd zapisu w bazie danych: {str(e)}'}), 500
        finally:
            conn.close()

    @admin_bp.route('/admin/api/agro-surowce/delete/<int:item_id>', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_delete_agro_surowiec(item_id):
        from flask import jsonify
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT nazwa FROM magazyn_agro_slownik_surowce WHERE id = %s', (item_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Nie znaleziono wybranego surowca.'}), 404

            nazwa = row[0]
            cursor.execute('DELETE FROM magazyn_agro_slownik_surowce WHERE id = %s', (item_id,))
            conn.commit()
            return jsonify({'success': True, 'message': f'Surowiec "{nazwa}" został usunięty.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Błąd usuwania z bazy danych: {str(e)}'}), 500
        finally:
            conn.close()

    @admin_bp.route('/admin/master/slownik-surowcow', methods=['GET'])
    @masteradmin_required
    def admin_master_slownik_surowcow():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nazwa FROM magazyn_agro_slownik_surowce ORDER BY nazwa ASC')
        surowce = [{'id': row[0], 'nazwa': row[1]} for row in cursor.fetchall()]
        conn.close()
        return render_template('admin_slownik_surowce.html', surowce=surowce)