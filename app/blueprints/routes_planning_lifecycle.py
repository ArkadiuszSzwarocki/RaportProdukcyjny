from datetime import date

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.db import get_db_connection, get_table_name
from app.decorators import hall_restricted, roles_required, masteradmin_required
from app.services.planning_service import PlanningService


def register_planning_lifecycle_routes(planning_bp, *, return_url_builder):
    def _build_context_return_url(linia, sekcja, data_planu):
        return url_for(
            'main.index',
            sekcja=sekcja or 'Zasyp',
            linia=linia or 'PSD',
            data=data_planu or str(date.today()),
        )

    @planning_bp.route('/przywroc_zlecenie_page/<int:id>', methods=['GET'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def przywroc_zlecenie_page(id):
        """Render a confirmation page for resuming an order."""
        linia = request.args.get('linia') or 'PSD'
        sekcja = request.args.get('sekcja') or 'Zasyp'
        data_planu = request.args.get('data') or request.args.get('data_planu')
        try:
            conn = get_db_connection()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(f'SELECT id, produkt, tonaz FROM {table_plan} WHERE id = %s', (id,))
            plan = cursor.fetchone()
            conn.close()

            if not plan:
                flash('Zlecenie nie istnieje', 'danger')
                return redirect(url_for('main.index'))

            plan_id, produkt, tonaz = plan[0], plan[1], plan[2]
            return render_template(
                'przywroc_zlecenie.html',
                id=plan_id,
                produkt=produkt,
                tonaz=tonaz,
                linia=linia,
                sekcja=sekcja,
                data_planu=data_planu,
            )
        except Exception as error:
            current_app.logger.error(f'Error loading restoration page: {error}')
            return redirect(url_for('main.index'))

    @planning_bp.route('/reanimate_zlecenie/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def reanimate_zlecenie(id):
        """Przywraca zakończone lub zarchiwizowane zlecenie do statusu zaplanowane."""
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        sekcja = request.args.get('sekcja') or request.form.get('sekcja') or 'Zasyp'
        data_planu = request.form.get('data_planu') or request.args.get('data') or str(date.today())

        current_app.logger.info('[REANIMATE] id=%s linia=%s sekcja=%s data=%s user=%s role=%s', id, linia, sekcja, data_planu, session.get('login'), session.get('rola'))
        success, message = PlanningService.resume_plan(id, linia=linia)
        flash(message, 'success' if success else 'warning')
        return redirect(_build_context_return_url(linia, sekcja, data_planu))

    @planning_bp.route('/przywroc_usunietego_zlecenia/<int:id>', methods=['POST'])
    @masteradmin_required
    def przywroc_usunietego_zlecenia(id):
        """Restore a deleted plan."""
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')
        success, message = PlanningService.restore_plan(id, linia=linia)
        return jsonify({'success': success, 'message': message}), 200 if success else 500

    @planning_bp.route('/zmien_status_zlecenia/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    @hall_restricted
    def zmien_status_zlecenia(id):
        """Change plan status."""
        status = request.form.get('status')
        linia = request.args.get('linia') or request.form.get('linia', 'PSD')

        if not status:
            flash('Nie podano statusu', 'warning')
            return redirect(return_url_builder())

        success, message = PlanningService.change_status(id, status, linia=linia)
        flash(message, 'success' if success else 'warning')
        return redirect(return_url_builder())

    @planning_bp.route('/usun_plan/<int:id>', methods=['POST'])
    @masteradmin_required
    def usun_plan(id):
        """Unified route for plan deletion (PSD/AGRO)."""
        linia = request.form.get('linia') or request.args.get('linia') or 'PSD'
        data_planu = request.form.get('data_planu') or request.args.get('data_planu') or str(date.today())
        tab = request.form.get('tab') or request.args.get('tab')

        if not tab:
            tab = 'agro' if linia.upper() == 'AGRO' else 'psd'

        current_app.logger.info(f'[PLAN-DELETE] Request to delete plan ID={id} (linia={linia}, tab={tab}, data={data_planu})')

        success, message = PlanningService.delete_plan(id, linia=linia)

        if success:
            flash(message, 'success')
        else:
            flash(message, 'error')

        return redirect(url_for('planista.panel_planisty', data=data_planu, linia=linia, tab=tab))