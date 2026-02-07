"""Planning and management routes (formerly in routes_api.py ZARZĄDZANIE section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from app.db import get_db_connection
from app.decorators import login_required, roles_required, admin_required
from app.services.planning_service import PlanningService
from app.services.plan_movement_service import PlanMovementService
import json

planning_bp = Blueprint('planning', __name__)


def bezpieczny_powrot():
    """Return to appropriate view based on user role."""
    role = session.get('rola', '')
    if role in ['lider', 'produkcja']:
        return url_for('panels.bufor_page')
    elif role == 'planista':
        return url_for('planista.panel_planisty', data=str(date.today()))
    elif role == 'admin':
        return url_for('admin.admin_panel')
    else:
        return url_for('app.index')


def log_plan_history(plan_id, action, details, user):
    """Log changes to plan for audit trail."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO plan_history (plan_id, action, details, user_login, timestamp) VALUES (%s, %s, %s, %s, NOW())",
            (plan_id, action, details, user)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


@planning_bp.route('/przywroc_zlecenie_page/<int:id>', methods=['GET'])
@roles_required('lider', 'admin')
def przywroc_zlecenie_page(id):
    """Render a confirmation popup for resuming/recovering an order."""
    sekcja = request.args.get('sekcja', 'Zasyp')
    produkt = None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT produkt FROM plan_produkcji WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            produkt = row[0]
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return render_template('przywroc_zlecenie.html', id=id, sekcja=sekcja, produkt=produkt)


@planning_bp.route('/przywroc_zlecenie/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def przywroc_zlecenie(id):
    """Resume a paused plan - delegated to PlanningService."""
    success, message = PlanningService.resume_plan(id)
    flash(message, 'success' if success else 'warning')
    return redirect(bezpieczny_powrot())


@planning_bp.route('/przywroc_usunietego_zlecenia/<int:id>', methods=['POST'])
@roles_required('planista', 'admin')
def przywroc_usunietego_zlecenia(id):
    """Restore (undelete) a deleted plan - delegated to PlanningService."""
    success, message = PlanningService.restore_plan(id)
    return jsonify({'success': success, 'message': message}), 200 if success else 500


@planning_bp.route('/zmien_status_zlecenia/<int:id>', methods=['POST'])
@login_required
def zmien_status_zlecenia(id):
    """Change plan status - delegated to PlanningService."""
    status = request.form.get('status')
    if not status:
        flash('Status jest wymagany.', 'warning')
        return redirect(bezpieczny_powrot())
    
    success, message = PlanningService.change_status(id, status)
    flash(message, 'success' if success else 'warning')
    return redirect(bezpieczny_powrot())


@planning_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def usun_plan(id):
    """Soft delete a plan - delegated to PlanningService."""
    success, message = PlanningService.delete_plan(id)
    flash(message, 'success' if success else 'warning')
    return redirect(bezpieczny_powrot())


@planning_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
@roles_required('planista', 'admin')
def dodaj_plan_zaawansowany():
    """Add plan with advanced options - delegated to PlanningService."""
    data_planu = request.form.get('data_planu')
    produkt = request.form.get('produkt')
    sekcja = request.form.get('sekcja')
    typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
    wymaga_oplaty = bool(request.form.get('wymaga_oplaty'))
    
    try:
        tonaz = int(float(request.form.get('tonaz', 0)))
    except Exception:
        tonaz = 0
    
    success, message, plan_id = PlanningService.create_plan(
        data_planu, produkt, tonaz, sekcja, typ, 
        status='zaplanowane', wymaga_oplaty=wymaga_oplaty
    )
    
    if not success:
        flash(message, 'warning')
    
    return redirect(url_for('planista.panel_planisty', data=data_planu))


@planning_bp.route('/dodaj_plan', methods=['POST'])
@roles_required('planista', 'admin', 'lider', 'produkcja', 'pracownik')
def dodaj_plan():
    """Add a plan (legacy simple add)."""
    data_planu = request.form.get('data_planu') or request.form.get('data') or str(date.today())
    from app.utils.validation import require_field
    
    # Get all fields - allow empty produkt since it comes from hidden field
    produkt = request.form.get('produkt', '').strip()
    try:
        tonaz = int(float(request.form.get('tonaz', 0)))
    except Exception:
        tonaz = 0
    sekcja = request.form.get('sekcja') or request.args.get('sekcja') or 'Nieprzydzielony'
    typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
    
    # Get plan_id if provided (from popup form)
    try:
        plan_id_str = request.form.get('plan_id', '').strip()
        plan_id_provided = int(plan_id_str) if plan_id_str else 0
    except Exception:
        plan_id_provided = 0
    
    # SUPER DETAILED LOGGING
    log_msg = f'[DODAJ_PLAN] POST received: sekcja={sekcja}, produkt={produkt}, tonaz={tonaz}, typ={typ}, plan_id={plan_id_provided}'
    try:
        current_app.logger.warning(log_msg)  # Use WARNING level so it shows
    except Exception:
        pass
    try:
        print(log_msg)  # Also print to console
    except Exception:
        pass
    
    # Validate required fields
    if not produkt:
        try:
            current_app.logger.warning(f'[DODAJ_PLAN] MISSING produkt - redirecting')
        except Exception:
            pass
        return redirect(bezpieczny_powrot())
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    zasyp_plan_id = None
    if tonaz > 0:
        # BUFFER LOGIC: 
        # - Szarża (Zasyp): Increases tonaz_rzeczywisty of PROVIDED plan (plan_id) + increases buffer (Workowanie)
        # - Paleta (Workowanie): Decreases buffer (Workowanie)
        
        if sekcja == 'Zasyp':
            try:
                current_app.logger.warning(f'[DODAJ_PLAN] Processing ZASYP szarża')
            except Exception:
                pass
            
            # SZARŻA: If plan_id is provided, use it directly. Otherwise search for plan.
            if plan_id_provided > 0:
                # Use provided plan_id
                zasyp_plan_id = plan_id_provided
                try:
                    current_app.logger.warning(f'[DODAJ_PLAN] Using PROVIDED plan_id={zasyp_plan_id}')
                except Exception:
                    pass
            else:
                # Find ANY Zasyp plan for this product
                try:
                    current_app.logger.warning(f'[DODAJ_PLAN] plan_id_provided=0, searching for Zasyp plan for produkt={produkt}')
                except Exception:
                    pass
                
                cursor.execute(
                    "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Zasyp' AND COALESCE(typ_produkcji,'')=%s ORDER BY id DESC LIMIT 1",
                    (data_planu, produkt, typ)
                )
                szarza_plan = cursor.fetchone()
                if szarza_plan:
                    zasyp_plan_id = szarza_plan[0]
                    try:
                        current_app.logger.warning(f'[DODAJ_PLAN] FOUND Zasyp plan: plan_id={zasyp_plan_id}')
                    except Exception:
                        pass
            
            if zasyp_plan_id:
                try:
                    current_app.logger.warning(f'[DODAJ_PLAN] ADDING szarża: plan_id={zasyp_plan_id}, tonaz={tonaz}')
                except Exception:
                    pass
                
                # Insert szarża into szarze table
                from datetime import datetime as _dt
                now = _dt.now()
                godzina = now.strftime('%H:%M:%S')
                
                pracownik_id = None
                if 'user_id' in session:
                    pracownik_id = session.get('user_id')
                
                cursor.execute(
                    "INSERT INTO szarze (plan_id, waga, data_dodania, godzina, pracownik_id, status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (zasyp_plan_id, tonaz, now, godzina, pracownik_id, 'zarejestowana')
                )
                
                # Increase szarża plan's tonaz_rzeczywisty
                cursor.execute(
                    "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id=%s",
                    (tonaz, zasyp_plan_id)
                )
                try:
                    current_app.logger.warning(f'[DODAJ_PLAN] Added szarża to plan {zasyp_plan_id}')
                except Exception:
                    pass
                
                # Zasyp and Workowanie work independently
                # No automatic increase of buffer
                
                conn.commit()
                conn.close()
                try:
                    current_app.logger.warning(f'[DODAJ_PLAN] SUCCESS: committed and returning')
                except Exception:
                    pass
                return redirect(bezpieczny_powrot())
            else:
                # No plan found and none provided - this is error for szarża!
                conn.close()
                try:
                    current_app.logger.warning(f'[DODAJ_PLAN] ERROR: No plan found for szarża. plan_id_provided={plan_id_provided}, produkt={produkt}')
                except Exception:
                    pass
                flash('Nie znaleziono planu do dodania szarży', 'error')
                return redirect(bezpieczny_powrot())
        
        elif sekcja == 'Workowanie':
            # PALETA: Find BUFFER (first/oldest open plan in Workowanie) to REMOVE from it
            cursor.execute(
                "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND status='w toku' AND COALESCE(typ_produkcji,'')=%s ORDER BY id LIMIT 1",
                (data_planu, produkt, typ)
            )
            buffer_plan = cursor.fetchone()
            if buffer_plan:
                zasyp_plan_id = buffer_plan[0]
                try:
                    current_app.logger.info(f'[DODAJ_PLAN] Removing paleta from buffer: plan_id={zasyp_plan_id}, tonaz={tonaz}')
                except Exception:
                    pass

                # Insert a new paleta record
                cursor.execute(
                    "INSERT INTO palety_workowanie (plan_id, waga, status) VALUES (%s, %s, %s)",
                    (zasyp_plan_id, tonaz, 'oczekuje')
                )
                
                # Decrease buffer tonaz_rzeczywisty
                cursor.execute(
                    "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) - %s WHERE id=%s",
                    (tonaz, zasyp_plan_id)
                )
                
                conn.commit()
                conn.close()
                return redirect(bezpieczny_powrot())
    
    # No open order found - create new planned order
    status = 'zaplanowane'
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, status, sekcja, nk, typ, 0))
    zasyp_plan_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
    
    # NEW: If sekcja is Zasyp, create corresponding Workowanie automatically
    if sekcja == 'Zasyp' and zasyp_plan_id:
        try:
            current_app.logger.info(f'[DODAJ_PLAN] Creating AUTO Workowanie for Zasyp plan_id={zasyp_plan_id}')
        except Exception:
            pass
        
        # Create corresponding Workowanie in status 'w toku'
        nk_work = nk + 1  # Sequence for Workowanie
        cursor.execute(
            "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (data_planu, produkt, 0, 'w toku', 'Workowanie', nk_work, typ, 0)
        )
    
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@planning_bp.route('/planista/bulk', methods=['GET'])
@roles_required('planista', 'admin')
def planista_bulk_page():
    """Render page for bulk adding plans."""
    wybrana_data = request.args.get('data', str(date.today()))
    return render_template('planista_bulk.html', wybrana_data=wybrana_data)


@planning_bp.route('/dodaj_plany_batch', methods=['POST'])
@roles_required('planista', 'admin')
def dodaj_plany_batch():
    """Add multiple plans in batch."""
    try:
        data = request.get_json(force=True)
    except Exception:
        data = {}
    data_planu = data.get('data_planu') or str(date.today())
    plans = data.get('plans') or []
    if not plans:
        return jsonify({'success': False, 'message': 'Brak planów w żądaniu'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Compute initial max sequence
        cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
        res = cursor.fetchone()
        nk = (res[0] if res and res[0] else 0)
        for idx, p in enumerate(plans, start=1):
            produkt = (p.get('produkt') or '').strip()
            try:
                tonaz = int(float(p.get('tonaz') or 0))
            except Exception:
                tonaz = 0
            typ = (p.get('typ_produkcji') or '').strip() or 'worki_zgrzewane_25'
            sekcja = p.get('sekcja') or 'Zasyp'
            nr = p.get('nr_receptury') or ''
            # Basic validation
            if not produkt:
                conn.rollback()
                conn.close()
                return jsonify({'success': False, 'message': f'Wiersz {idx}: brak nazwy produktu'})
            if not (isinstance(tonaz, int) and tonaz > 0):
                conn.rollback()
                conn.close()
                return jsonify({'success': False, 'message': f'Wiersz {idx}: nieprawidłowy tonaż'})
            if not typ:
                conn.rollback()
                conn.close()
                return jsonify({'success': False, 'message': f'Wiersz {idx}: brak typu produkcji'})
            nk += 1
            cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', sekcja, nk, typ, nr, 0))
            
            # NEW: If sekcja is Zasyp, create corresponding Workowanie automatically
            if sekcja == 'Zasyp':
                nk += 1  # Increase sequence for Workowanie
                cursor.execute(
                    "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (data_planu, produkt, 0, 'w toku', 'Workowanie', nk, typ, 0)
                )
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Failed to insert batch plans: %s', e)
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd podczas zapisu planów'})
    try:
        conn.close()
    except Exception:
        pass
    return jsonify({'success': True})


@planning_bp.route('/przenies_zlecenie/<int:id>', methods=['POST'])
@login_required
def przenies_zlecenie(id):
    """Move a plan to a different date - delegated to PlanningService."""
    nowa_data = request.form.get('nowa_data')
    if not nowa_data:
        flash('Nowa data jest wymagana.', 'warning')
        return redirect(bezpieczny_powrot())
    
    success, message = PlanningService.reschedule_plan(id, nowa_data)
    flash(message, 'success' if success else 'warning')
    return redirect(bezpieczny_powrot())


# Endpoint '/przenies_do_jakosc' removed — disinfection is planned by lab
# and reported to planner; we no longer use server-side "move to Jakość" mechanism.


@planning_bp.route('/przesun_zlecenie/<int:id>/<kierunek>', methods=['POST'])
@roles_required('planista', 'admin')
def przesun_zlecenie(id, kierunek):
    """Move a plan up or down in the sequence - delegated to PlanMovementService."""
    data = request.args.get('data', str(date.today()))
    success, message = PlanMovementService.shift_plan_order(id, kierunek)
    if not success:
        flash(message, 'warning')
    return redirect(url_for('planista.panel_planisty', data=data))


@planning_bp.route('/edytuj_plan/<int:id>', methods=['POST'])
@roles_required('planista', 'admin')
def edytuj_plan(id):
    """Save plan edits: product, tonnage, section, date."""
    from app.utils.validation import require_field
    produkt = request.form.get('produkt')
    tonaz = request.form.get('tonaz')
    sekcja = request.form.get('sekcja')
    data_planu = request.form.get('data_planu')
    try:
        tonaz_val = int(float(tonaz)) if tonaz is not None and tonaz != '' else None
    except Exception:
        tonaz_val = None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if exists
        cursor.execute("SELECT id, status FROM plan_produkcji WHERE id=%s", (id,))
        r = cursor.fetchone()
        if not r:
            flash('Nie znaleziono zlecenia', 'warning')
            return redirect(bezpieczny_powrot())
        if r[1] in ['w toku', 'zakonczone']:
            flash('Nie można edytować zleceń w toku lub zakończonych', 'warning')
            return redirect(bezpieczny_powrot())

        updates = []
        params = []
        if produkt is not None:
            updates.append('produkt=%s')
            params.append(produkt)
        if tonaz_val is not None:
            updates.append('tonaz=%s')
            params.append(tonaz_val)
        if sekcja:
            updates.append('sekcja=%s')
            params.append(sekcja)
        if data_planu:
            # if changing date, set new sequence at end of day
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1
            updates.append('data_planu=%s')
            params.append(data_planu)
            updates.append('kolejnosc=%s')
            params.append(nk)

        if updates:
            sql = f"UPDATE plan_produkcji SET {', '.join(updates)} WHERE id=%s"
            params.append(id)
            cursor.execute(sql, tuple(params))
            conn.commit()
            flash('Zlecenie zaktualizowane', 'success')
    except Exception:
        current_app.logger.exception('Failed to edit plan %s', id)
        try:
            conn.rollback()
        except Exception:
            pass
        flash('Błąd podczas zapisu zmian', 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return redirect(bezpieczny_powrot())


@planning_bp.route('/edytuj_plan_ajax', methods=['POST'])
@roles_required('planista', 'admin')
def edytuj_plan_ajax():
    """Edit plan via AJAX."""
    try:
        data = request.get_json(force=True)
    except Exception:
        data = request.form.to_dict()
    id = data.get('id')
    if not id:
        return jsonify({'success': False, 'message': 'Brak id'}), 400
    try:
        pid = int(id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

    produkt = data.get('produkt')
    tonaz = data.get('tonaz')
    sekcja = data.get('sekcja')
    data_planu = data.get('data_planu')

    try:
        tonaz_val = int(float(tonaz)) if tonaz is not None and str(tonaz).strip() != '' else None
    except Exception:
        tonaz_val = None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, produkt, tonaz, sekcja, data_planu, status FROM plan_produkcji WHERE id=%s", (pid,))
        before = cursor.fetchone()
        if not before:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404
        if before[5] in ['w toku', 'zakonczone']:
            conn.close()
            return jsonify({'success': False, 'message': 'Nie można edytować zleceń w toku lub zakończonych'}), 403

        updates = []
        params = []
        changes = {}
        if produkt is not None and produkt != before[1]:
            updates.append('produkt=%s')
            params.append(produkt)
            changes['produkt'] = {'before': before[1], 'after': produkt}
        if tonaz_val is not None and tonaz_val != (before[2] or 0):
            updates.append('tonaz=%s')
            params.append(tonaz_val)
            changes['tonaz'] = {'before': before[2], 'after': tonaz_val}
        if sekcja and sekcja != before[3]:
            updates.append('sekcja=%s')
            params.append(sekcja)
            changes['sekcja'] = {'before': before[3], 'after': sekcja}
        if data_planu and data_planu != str(before[4]):
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1
            updates.append('data_planu=%s')
            params.append(data_planu)
            updates.append('kolejnosc=%s')
            params.append(nk)
            changes['data_planu'] = {'before': str(before[4]), 'after': data_planu}

        if updates:
            sql = f"UPDATE plan_produkcji SET {', '.join(updates)} WHERE id=%s"
            params.append(pid)
            cursor.execute(sql, tuple(params))
            conn.commit()
            # log history
            try:
                user_login = session.get('login') or session.get('imie_nazwisko')
            except Exception:
                user_login = None
            try:
                log_plan_history(pid, 'edit', json.dumps(changes, default=str, ensure_ascii=False), user_login)
            except Exception:
                pass
            conn.close()
            return jsonify({'success': True, 'message': 'Zaktualizowano', 'changes': changes})
        conn.close()
        return jsonify({'success': True, 'message': 'Brak zmian'})
    except Exception as e:
        current_app.logger.exception('Error edytuj_plan_ajax')
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500


@planning_bp.route('/przenies_zlecenie_ajax', methods=['POST'])
@roles_required('planista', 'admin')
def przenies_zlecenie_ajax():
    """Move a plan to different date via AJAX - delegated to PlanningService."""
    try:
        data = request.get_json(force=True)
    except Exception:
        data = request.form.to_dict()
    
    id = data.get('id')
    to_date = data.get('to_date')
    if not id or not to_date:
        return jsonify({'success': False, 'message': 'Brak parametrów'}), 400
    
    try:
        pid = int(id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

    success, message = PlanningService.reschedule_plan(pid, to_date)
    
    if success:
        # Get old date and log history
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT data_planu FROM plan_produkcji WHERE id=%s", (pid,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                old_date = row[0]
                user_login = session.get('login') or session.get('imie_nazwisko')
                log_plan_history(pid, 'move', json.dumps({'from': str(old_date), 'to': to_date}, ensure_ascii=False), user_login)
        except Exception:
            pass
    
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message}), status_code


@planning_bp.route('/przesun_zlecenie_ajax', methods=['POST'])
@roles_required('planista', 'admin')
def przesun_zlecenie_ajax():
    """Move a plan up/down in sequence via AJAX - delegated to PlanMovementService."""
    try:
        data = request.get_json(force=True)
    except Exception:
        data = request.form.to_dict()
    
    id = data.get('id')
    kierunek = data.get('kierunek')
    if not id or not kierunek:
        return jsonify({'success': False, 'message': 'Brak parametrów'}), 400
    
    try:
        pid = int(id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

    success, message = PlanMovementService.shift_plan_order(pid, kierunek)
    
    if success:
        # Log history
        try:
            user_login = session.get('login') or session.get('imie_nazwisko')
            log_plan_history(pid, 'reorder', json.dumps({'direction': kierunek}, ensure_ascii=False), user_login)
        except Exception:
            pass
    
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': message}), status_code


@planning_bp.route('/usun_plan_ajax/<int:id>', methods=['POST'])
@roles_required('planista', 'admin', 'lider')
def api_usun_plan(id):
    """Soft delete plan via AJAX - delegated to PlanningService."""
    try:
        success, message = PlanningService.delete_plan(id)
        
        if success:
            # Log history if deletion was successful
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT produkt, data_planu, tonaz FROM plan_produkcji WHERE id=%s", (id,))
                res = cursor.fetchone()
                conn.close()
                
                if res:
                    details = {'produkt': res[0], 'data_planu': str(res[1]), 'tonaz': res[2]}
                    user_login = session.get('login') or session.get('imie_nazwisko')
                    log_plan_history(id, 'soft_delete', json.dumps(details, ensure_ascii=False), user_login)
            except Exception:
                pass
        
        return jsonify({'success': success, 'message': message}), 200 if success else 400
        
    except Exception:
        current_app.logger.exception(f'Error deleting plan {id} via AJAX')
        return jsonify({'success': False, 'message': 'Błąd przy usuwaniu zlecenia.'}), 500


# ================= JAKOŚĆ -> DODAJ DO PLANÓW =================
@planning_bp.route('/jakosc/dodaj_do_planow/<int:id>', methods=['POST'])
@roles_required('planista', 'admin')
def jakosc_dodaj_do_planow(id):
    """Create a scheduled production order based on a quality order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT produkt, tonaz, typ_produkcji FROM plan_produkcji WHERE id=%s", (id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        flash('Nie znaleziono zlecenia jakościowego', 'danger')
        return redirect(bezpieczny_powrot())

    produkt, tonaz, typ = row[0], row[1] or 0, row[2] if len(row) > 2 else None
    data_planu = request.form.get('data_planu') or request.form.get('data_powrot') or str(date.today())
    # Calculate new sequence
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', 'Zasyp', nk, typ, 0))
    zasyp_plan_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
    
    # NEW: Create corresponding Workowanie automatically
    if zasyp_plan_id:
        nk_work = nk + 1
        cursor.execute(
            "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (data_planu, produkt, 0, 'w toku', 'Workowanie', nk_work, typ, 0)
        )
    
    conn.commit()
    conn.close()
    flash('Zlecenie dodane do planów', 'success')
    return redirect(bezpieczny_powrot())


