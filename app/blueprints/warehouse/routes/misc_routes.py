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


def _parse_data_produkcji_input(raw_value):
    """Validate optional production date input (YYYY-MM-DD)."""
    value = str(raw_value or '').strip()
    if not value:
        return None
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError as error:
        raise ValueError('Nieprawidlowy format daty produkcji (oczekiwano RRRR-MM-DD)') from error
    return value

def register_misc_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):
    @warehouse_bp.route('/api/update_workowanie_data_produkcji', methods=['POST'])
    @roles_required('lider', 'admin', 'magazynier')
    def update_workowanie_data_produkcji():
        """Update production date for a Workowanie order (also allowed while in progress)."""
        data = request.get_json(silent=True) or {}
        plan_id_raw = data.get('plan_id')
        linia = str(resolve_payload_linia(data)).upper()
    
        try:
            plan_id = int(plan_id_raw)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidlowe id zlecenia'}), 400
    
        try:
            data_produkcji = _parse_data_produkcji_input(data.get('data_produkcji'))
        except ValueError as error:
            return jsonify({'success': False, 'message': str(error)}), 400
    
        if not data_produkcji:
            return jsonify({'success': False, 'message': 'Brak daty produkcji'}), 400
    
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            table_plan = get_table_name('plan_produkcji', linia)
    
            cursor.execute(f"SELECT sekcja, status FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404
    
            sekcja = str(row[0] or '')
            if sekcja.lower() != 'workowanie':
                return jsonify({'success': False, 'message': 'Zmiana daty jest dostepna tylko dla zlecen Workowanie'}), 400
    
            cursor.execute(f"UPDATE {table_plan} SET data_produkcji=%s WHERE id=%s", (data_produkcji, plan_id))
            conn.commit()
    
            current_app.logger.info(
                'Zmieniono data_produkcji=%s dla zlecenia Workowanie id=%s (linia=%s, user=%s)',
                data_produkcji,
                plan_id,
                linia,
                session.get('login'),
            )
            audit_log('Zmiana daty produkcji (Workowanie)', f'plan_id={plan_id}, data_produkcji={data_produkcji}, linia={linia}')
    
            return jsonify({
                'success': True,
                'message': f'Ustawiono date produkcji: {data_produkcji}',
                'data_produkcji': data_produkcji,
            })
        except Exception as error:
            current_app.logger.exception('Failed to update data_produkcji for Workowanie plan %s: %s', plan_id, error)
            return jsonify({'success': False, 'message': f'Blad: {error}'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
