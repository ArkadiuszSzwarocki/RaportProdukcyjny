from datetime import date

from flask import flash, jsonify, redirect, request

from app.db import get_db_connection, get_table_name
from app.decorators import roles_required


def register_planning_quality_routes(planning_bp, *, return_url_builder):
    @planning_bp.route('/jakosc/dodaj_do_planow/<int:id>', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def jakosc_dodaj_do_planow(id):
        """Create a scheduled production order based on a quality order."""
        linia = request.args.get('linia') or request.form.get('linia') or 'PSD'
        conn = get_db_connection()
        table_plan = get_table_name('plan_produkcji', linia)
        cursor = conn.cursor()
        cursor.execute(f"SELECT produkt, tonaz, typ_produkcji FROM {table_plan} WHERE id=%s", (id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            flash('Nie znaleziono zlecenia jakościowego', 'danger')
            return redirect(return_url_builder())

        produkt, tonaz, typ = row[0], row[1] or 0, row[2] if len(row) > 2 else None
        data_planu = request.form.get('data_planu') or request.form.get('data_powrot') or str(date.today())

        cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja='Zasyp'", (data_planu,))
        result = cursor.fetchone()
        next_zasyp = (result[0] if result and result[0] else 0) + 1

        cursor.execute(
            f"INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (data_planu, produkt, tonaz, 'zaplanowane', 'Zasyp', next_zasyp, typ, 0),
        )
        zasyp_plan_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None

        if zasyp_plan_id:
            cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja='Workowanie'", (data_planu,))
            work_result = cursor.fetchone()
            next_workowanie = (work_result[0] if work_result and work_result[0] else 0) + 1
            cursor.execute(
                f"INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (data_planu, produkt, 0, 'w toku', 'Workowanie', next_workowanie, typ, 0),
            )

        conn.commit()
        conn.close()
        flash('Zlecenie dodane do planów', 'success')
        return redirect(return_url_builder())

    @planning_bp.route('/reorder_plans_bulk', methods=['POST'])
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def reorder_plans_bulk():
        """Reorder plans via drag-and-drop."""
        try:
            data = request.get_json(force=True)
        except Exception:
            data = request.form.to_dict()

        plan_ids = data.get('plan_ids', [])
        data_planu = data.get('data')
        linia = data.get('linia', 'PSD')
        if not plan_ids or not isinstance(plan_ids, list):
            return jsonify({'success': False, 'message': 'Brak plan_ids'}), 400
        if not data_planu:
            return jsonify({'success': False, 'message': 'Brak data'}), 400

        conn = None
        try:
            conn = get_db_connection()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()

            for plan_id in plan_ids:
                cursor.execute(
                    f"SELECT status FROM {table_plan} WHERE id=%s AND DATE(data_planu)=%s",
                    (int(plan_id), data_planu),
                )
                row = cursor.fetchone()
                if row:
                    status = row[0]
                    if status in ['w toku', 'zakonczone']:
                        conn.close()
                        return jsonify({'success': False, 'message': f'Plan {int(plan_id)} ma status "{status}" — nie można reorderować planów w toku lub zakończonych'}), 403
                else:
                    conn.close()
                    return jsonify({'success': False, 'message': f'Plan {int(plan_id)} nie znaleziony dla daty {data_planu}'}), 404

            for index, plan_id in enumerate(plan_ids, 1):
                cursor.execute(
                    f"UPDATE {table_plan} SET kolejnosc=%s WHERE id=%s AND DATE(data_planu)=%s AND status='zaplanowane'",
                    (index, int(plan_id), data_planu),
                )

            # Renormalize to ensure consistent numbering and handle potential conflicts
            from app.services.plan_movement_service import PlanMovementService
            PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, None if linia.upper() == 'AGRO' else 'Zasyp')

            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'OK'}), 200

        except Exception as error:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return jsonify({'success': False, 'message': str(error)}), 500