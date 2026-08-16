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

    @warehouse_bp.route('/wazenie_magazyn/<int:paleta_id>', methods=['POST'])
    @login_required
    def wazenie_magazyn(paleta_id):
        """Weigh paleta in warehouse and update weight."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_mag = get_table_name('magazyn_palety', linia)
    
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            brutto = int(float(request.form.get('waga_brutto', '0').replace(',', '.')))
        except Exception:
            brutto = 0
    
        cursor.execute(f"SELECT tara, plan_id, nr_palety, nr_plomby FROM {table_pal} WHERE id=%s", (paleta_id,))
        res = cursor.fetchone()
        if res:
            tara, plan_id, nr_palety, nr_plomby = res
            netto = brutto - int(tara)
            if netto < 0:
                netto = 0
            try:
                cursor.execute(f"UPDATE {table_pal} SET waga_brutto=%s WHERE id=%s", (brutto, paleta_id))
            except Exception as error:
                current_app.logger.error('Failed to store brutto for paleta %s: %s', paleta_id, error, exc_info=True)
            cursor.execute(f"SELECT data_planu, produkt FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (row[0], row[1]))
                mp = cursor.fetchone()
                mp_id = mp[0] if mp else None
                cursor.execute(f"SELECT id FROM {table_mag} WHERE paleta_workowanie_id=%s", (paleta_id,))
                exists = cursor.fetchone()
                if not exists:
                    try:
                        cursor.execute(
                            f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_palety, nr_plomby) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (paleta_id, mp_id, row[0], row[1], netto, brutto, tara, session.get('login'), nr_palety, nr_plomby),
                        )
                    except mysql.connector.IntegrityError:
                        pass
                else:
                    cursor.execute(
                        f"UPDATE {table_mag} SET waga_netto=%s, waga_brutto=%s, tara=%s, data_potwierdzenia=NOW() WHERE paleta_workowanie_id=%s",
                        (netto, brutto, tara, paleta_id),
                    )
                cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM {table_mag} WHERE plan_id = {table_plan}.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                    (row[0], row[1]),
                )
    
        conn.commit()
        conn.close()
        return redirect(safe_return())

