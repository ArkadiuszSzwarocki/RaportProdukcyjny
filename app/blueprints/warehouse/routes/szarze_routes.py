from datetime import date, datetime
import os
import threading

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning.status import PlanningStatusService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id


def register_szarze_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):
    @warehouse_bp.route('/confirm_delete_szarze_page/<int:szarza_id>', methods=['GET'], endpoint='confirm_delete_szarze_page')
    @warehouse_bp.route('/confirm_delete_zasyp_page/<int:szarza_id>', methods=['GET'], endpoint='confirm_delete_zasyp_page')
    @login_required
    def confirm_delete_szarze_page(szarza_id):
        """Render delete confirmation for zasyp (legacy route name)."""
        linia = resolve_request_linia()
        sekcja = request.args.get('sekcja') or 'Zasyp'
        data_value = request.args.get('data') or request.args.get('data_planu') or str(date.today())
        return render_template(
            'warehouse/popups/delete_zasyp_confirm.html',
            szarza_id=szarza_id,
            zasyp_id=szarza_id,
            linia=linia,
            sekcja=sekcja,
            data_planu=data_value,
        )

    @warehouse_bp.route('/edytuj_szarze_page/<int:szarza_id>', methods=['GET'], endpoint='edytuj_szarze_page')
    @warehouse_bp.route('/edytuj_zasyp_page/<int:szarza_id>', methods=['GET'], endpoint='edytuj_zasyp_page')
    @login_required
    def edytuj_szarze_page(szarza_id):
        """Render form for editing zasyp notes (uwagi)."""
        linia = str(resolve_request_linia()).upper()
        table_zasypy = get_table_name('szarze', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        uwagi = ''
        try:
            cursor.execute(f"SELECT uwagi FROM {table_zasypy} WHERE id=%s", (szarza_id,))
            row = cursor.fetchone()
            if row:
                uwagi = row[0] or ''
        except Exception as error:
            current_app.logger.error('Failed to load zasyp %s for edit page: %s', szarza_id, error, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
        data_value = request.args.get('data') or str(date.today())
        sekcja = request.args.get('sekcja', 'Zasyp')
        return render_template('warehouse/popups/edit_zasyp.html', szarza_id=szarza_id, zasyp_id=szarza_id, uwagi=uwagi, linia=linia, data=data_value, sekcja=sekcja)

    @warehouse_bp.route('/edytuj_szarze/<int:szarza_id>', methods=['POST'], endpoint='edytuj_szarze')
    @warehouse_bp.route('/edytuj_zasyp/<int:szarza_id>', methods=['POST'], endpoint='edytuj_zasyp')
    @login_required
    def edytuj_szarze(szarza_id):
        """Save zasyp notes (uwagi) to DB (legacy route name)."""
        new_uwagi = request.form.get('uwagi', '')
        linia = str(resolve_request_linia()).upper()
        table_zasypy = get_table_name('szarze', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"UPDATE {table_zasypy} SET uwagi=%s WHERE id=%s", (new_uwagi, szarza_id))
            conn.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Zapisano notatkę', 'szarza_id': szarza_id, 'zasyp_id': szarza_id}), 200
            flash('Zapisano notatkę do zasypu', 'success')
        except Exception as error:
            current_app.logger.error('Failed to save uwagi for zasyp %s: %s', szarza_id, error, exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Błąd zapisu notatki'}), 500
            flash('Błąd zapisu notatki', 'danger')
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
        return redirect(safe_return())

    @warehouse_bp.route('/usun_szarze/<int:id>', methods=['POST'], endpoint='usun_szarze')
    @warehouse_bp.route('/usun_zasyp/<int:id>', methods=['POST'], endpoint='usun_zasyp')
    @roles_required('lider', 'admin')
    def usun_szarze(id):
        """Delete zasyp from Zasyp section (legacy route name)."""
        linia = str(resolve_request_linia()).upper()
        table_zasypy = get_table_name('szarze', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT plan_id FROM {table_zasypy} WHERE id=%s", (id,))
            res = cursor.fetchone()
            if res:
                plan_id = res[0]
                cursor.execute(f"DELETE FROM {table_zasypy} WHERE id=%s", (id,))
                cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                    f"COALESCE((SELECT SUM(waga) FROM {table_zasypy} WHERE plan_id = %s), 0) + "
                    f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                    "WHERE id = %s",
                    (plan_id, plan_id, plan_id),
                )
                conn.commit()
        finally:
            conn.close()
    
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Zasyp usunięty'}), 200
    
        return redirect(safe_return())

