from flask import render_template, request

from app.db import get_db_connection
from app.decorators import dynamic_role_required


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
        conn.close()

        return render_template('ustawienia_produkcja.html', zlecenia=zlecenia, roles=roles, linia=linia)