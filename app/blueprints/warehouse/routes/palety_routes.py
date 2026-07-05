from flask import jsonify
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

from .printing_routes import _select_preferred_printer
from .misc_routes import _parse_data_produkcji_input
from .palety_helpers import _resolve_plan_id_for_paleta

def _resolve_plan_id_for_paleta(cursor, paleta_id, linia, requested_plan_id=None):
    """Resolve Workowanie plan_id for a pallet id from magazyn/buffer tables safely."""
    table_pal = get_table_name('palety_workowanie', linia)
    table_mag = get_table_name('magazyn_palety', linia)

    requested_id = None
    try:
        if requested_plan_id not in (None, '', 'None'):
            requested_id = int(requested_plan_id)
    except Exception:
        requested_id = None

    if requested_id:
        # Validate that requested plan_id really belongs to this pallet.
        cursor.execute(
            f"SELECT 1 FROM {table_mag} WHERE (id=%s OR paleta_workowanie_id=%s) AND plan_id=%s LIMIT 1",
            (paleta_id, paleta_id, requested_id),
        )
        if cursor.fetchone():
            return requested_id

        cursor.execute(
            f"SELECT 1 FROM {table_pal} WHERE id=%s AND plan_id=%s LIMIT 1",
            (paleta_id, requested_id),
        )
        if cursor.fetchone():
            return requested_id

    # First check magazyn table by confirmed pallet id/pointer.
    # This avoids id-collision with palety_workowanie IDs.
    cursor.execute(
        f'''
        SELECT COALESCE(mp.plan_id, pw.plan_id)
        FROM {table_mag} mp
        LEFT JOIN {table_pal} pw ON pw.id = mp.paleta_workowanie_id
        WHERE mp.id = %s OR mp.paleta_workowanie_id = %s
        ORDER BY CASE WHEN mp.id = %s THEN 0 ELSE 1 END, mp.id DESC
        LIMIT 1
        ''',
        (paleta_id, paleta_id, paleta_id),
    )
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])

    cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])

    return None

def register_palety_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):
    @warehouse_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
    @login_required
    def dodaj_palete(plan_id):
        """Add paleta (package) to Workowanie buffer."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        waga_palety = request.form.get('waga_palety', '0')
        nr_plomby = request.form.get('nr_plomby')
        data_produkcji = request.form.get('data_produkcji')
        printer_ip = request.form.get('printer_ip')
        printer_name = request.form.get('printer_name')
        user_login = session.get('login', 'System')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        app_obj = current_app._get_current_object()
        
        result, status_code, redirect_url = WarehousePalletService.dodaj_palete(
            plan_id, linia, waga_palety, nr_plomby, data_produkcji,
            printer_ip, printer_name, user_login, app_obj, is_ajax, safe_return()
        )
        
        if is_ajax:
            return jsonify({'success': status_code < 400, 'message': result}), status_code
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())

    @warehouse_bp.route('/dodaj_palete_page/<int:plan_id>', methods=['GET'])
    @login_required
    def dodaj_palete_page(plan_id):
        """Render form for adding paleta."""
        # This endpoint is intended to be loaded into a modal via AJAX (data-slide).
        # If accessed directly (full-page navigation), redirect back to a safe page
        # to avoid exposing the popup as a standalone page.
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return redirect(safe_return())
        linia = str(resolve_request_linia()).upper()
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        produkt = None
        sekcja = None
        typ = None
        data_produkcji = date.today().isoformat()
        try:
            cursor.execute(f"SELECT produkt, sekcja, typ_produkcji, data_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
            row = cursor.fetchone()
            if row:
                produkt, sekcja, typ = row[0], row[1], row[2]
                plan_data_produkcji = row[3] if len(row) > 3 else None
                if plan_data_produkcji:
                    if hasattr(plan_data_produkcji, 'strftime'):
                        data_produkcji = plan_data_produkcji.strftime('%Y-%m-%d')
                    else:
                        data_produkcji = str(plan_data_produkcji)
        except Exception as error:
            current_app.logger.error('Failed to fetch plan %s for dodaj_palete_page: %s', plan_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return render_template(
            'warehouse/popups/add_pallet.html',
            plan_id=plan_id,
            produkt=produkt,
            sekcja=sekcja,
            typ=typ,
            linia=linia,
            data_produkcji=data_produkcji,
        )

    @warehouse_bp.route('/edytuj_palete_page/<int:paleta_id>', methods=['GET'])
    @login_required
    def edytuj_palete_page(paleta_id):
        """Render form for editing paleta weight."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        waga = None
        sekcja = None
        try:
            cursor.execute(f"SELECT waga, plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
            row = cursor.fetchone()
            if row:
                waga = row[0]
                plan_id = row[1]
                cursor.execute(f"SELECT sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
                r2 = cursor.fetchone()
                if r2:
                    sekcja = r2[0]
        except Exception as error:
            current_app.logger.error('Failed to load paleta %s for edit page: %s', paleta_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return render_template('warehouse/popups/edit_pallet.html', paleta_id=paleta_id, waga=waga, sekcja=sekcja, linia=linia)

    @warehouse_bp.route('/confirm_delete_palete_page/<int:paleta_id>', methods=['GET'])
    @login_required
    def confirm_delete_palete_page(paleta_id):
        """Render delete confirmation for paleta."""
        linia = resolve_request_linia()
        source = request.args.get('source', '')
        return render_template('warehouse/popups/delete_pallet_confirm.html', paleta_id=paleta_id, linia=linia, source=source)

    @warehouse_bp.route('/potwierdz_palete_page/<int:paleta_id>', methods=['GET'])
    @login_required
    def potwierdz_palete_page(paleta_id):
        """Render form for confirming paleta acceptance."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        waga = None
        try:
            cursor.execute(f"SELECT waga, waga_brutto, tara FROM {table_pal} WHERE id=%s", (paleta_id,))
            row = cursor.fetchone()
            if row:
                waga = row[0]
        except Exception as error:
            current_app.logger.error('Failed to load paleta %s for potwierdz_palete_page: %s', paleta_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        dzisiaj_iso = date.today().isoformat()
        return render_template('warehouse/popups/confirm_pallet.html', paleta_id=paleta_id, waga=waga, linia=linia, dzisiaj_iso=dzisiaj_iso)

    @warehouse_bp.route('/potwierdz_palete/<int:paleta_id>', methods=['POST'])
    @login_required
    def potwierdz_palete(paleta_id):
        """Confirm paleta and move it to Magazyn."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        user_login = session.get('login', 'System')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        app_obj = current_app._get_current_object()
        
        result, status_code, redirect_url = WarehousePalletService.potwierdz_palete(
            paleta_id, linia, user_login, app_obj,
            update_paleta_workowanie, update_paleta_magazyn, is_ajax, safe_return()
        )
        
        if is_ajax:
            return jsonify({'success': status_code < 400, 'message': result}), status_code
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())

    @warehouse_bp.route('/usun_palete/<int:paleta_id>', methods=['POST'])
    @roles_required('lider', 'admin')
    def usun_palete(paleta_id):
        """Delete unconfirmed paleta."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        user_login = session.get('login', 'System')
        is_ajax = False
        
        result, status_code, redirect_url = WarehousePalletService.usun_palete(
            paleta_id, linia, user_login, is_ajax, safe_return()
        )
        
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())

    @warehouse_bp.route('/edytuj_palete/<int:paleta_id>', methods=['POST'])
    @roles_required('magazynier', 'lider', 'admin')
    def edytuj_palete(paleta_id):
        """Edit paleta weight."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        waga_palety = request.form.get('waga_palety', '0')
        user_login = session.get('login', 'System')
        is_ajax = False
        
        result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
            paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return()
        )
        
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())

    @warehouse_bp.route('/api/edytuj_palete_ajax/<int:paleta_id>', methods=['POST'])
    @roles_required('magazynier', 'produkcja', 'lider', 'admin')
    def edytuj_palete_ajax(paleta_id):
        """Edit paleta weight (AJAX)."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        try:
            req_data = request.get_json() or {}
        except Exception:
            req_data = {}
        waga_palety = req_data.get('waga_palety', '0')
        user_login = session.get('login', 'System')
        is_ajax = True
        
        result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
            paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return()
        )
        
        return jsonify({'success': status_code < 400, 'message': result}), status_code

    @warehouse_bp.route('/api/usun_palete_ajax/<int:paleta_id>', methods=['POST'])
    @roles_required('produkcja', 'lider', 'admin')
    def usun_palete_ajax(paleta_id):
        """Delete paleta (AJAX)."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        user_login = session.get('login', 'System')
        is_ajax = True
        
        result, status_code, redirect_url = WarehousePalletService.usun_palete(
            paleta_id, linia, user_login, is_ajax, safe_return()
        )
        
        return jsonify({'success': status_code < 400, 'message': result}), status_code

    @warehouse_bp.route('/cofnij_palete/<int:plan_id>', methods=['POST'])
    @roles_required('produkcja', 'lider', 'admin', 'masteradmin')
    def cofnij_palete(plan_id):
        """Delete the latest unconfirmed paleta for a given plan."""
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        conn = get_db_connection()
        cursor = conn.cursor()
        paleta_id = None
        table_pal = get_table_name('palety_workowanie', linia)
        try:
            cursor.execute(f"SELECT id FROM {get_table_name('plan_produkcji', linia)} WHERE id=%s", (plan_id,))
            if cursor.fetchone():
                cursor.execute(f"SELECT id FROM {table_pal} WHERE plan_id=%s ORDER BY id DESC LIMIT 1", (plan_id,))
                row = cursor.fetchone()
                if row:
                    paleta_id = row[0]
        except Exception as error:
            current_app.logger.error('Failed to find latest paleta for plan %s: %s', plan_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if not paleta_id:
            flash("Brak palet do cofnięcia lub wystąpił błąd.", "error")
            return redirect(safe_return())

        user_login = session.get('login', 'System')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        result, status_code, redirect_url = WarehousePalletService.usun_palete(
            paleta_id, linia, user_login, is_ajax, safe_return()
        )
        
        if is_ajax:
            return jsonify({'success': status_code < 400, 'message': result}), status_code
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())
