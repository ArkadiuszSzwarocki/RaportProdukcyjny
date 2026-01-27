from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from utils.validation import require_field
import logging
import json
from datetime import date, datetime, timedelta, time
from io import BytesIO
from db import get_db_connection
from dto.paleta import PaletaDTO
from decorators import login_required, roles_required
from services.raport_service import RaportService

api_bp = Blueprint('api', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('index', sekcja=sekcja, data=data)

# ================= PRODUKCJA =================

@api_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status FROM plan_produkcji WHERE id=%s", (id,))
    z = cursor.fetchone()
    
    if z:
        produkt, tonaz, sekcja, data_planu, typ, status_obecny = z
        if status_obecny != 'w toku':
            cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
            cursor.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW(), real_stop=NULL WHERE id=%s", (id,))
        
        if sekcja == 'Zasyp' and status_obecny == 'zaplanowane':
            cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND typ_produkcji=%s", (data_planu, produkt, typ))
            istniejace = cursor.fetchone()
            if not istniejace:
                cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
                res = cursor.fetchone()
                mk = res[0] if res and res[0] else 0
                nk = mk + 1
                cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji) VALUES (%s, 'Workowanie', %s, %s, 'zaplanowane', %s, %s)", (data_planu, produkt, tonaz, nk, typ))
            else:
                cursor.execute("UPDATE plan_produkcji SET tonaz=%s WHERE id=%s", (tonaz, istniejace[0]))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    final_tonaz = request.form.get('final_tonaz')
    wyjasnienie = request.form.get('wyjasnienie')
    rzeczywista_waga = 0
    if final_tonaz:
        try:
            rzeczywista_waga = int(float(final_tonaz.replace(',', '.')))
        except Exception:
            pass

    sql = "UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW()"
    params = []
    if rzeczywista_waga > 0:
        sql += ", tonaz_rzeczywisty=%s"
        params.append(rzeczywista_waga)
    if wyjasnienie:
        sql += ", wyjasnienie_rozbieznosci=%s"
        params.append(wyjasnienie)
    sql += " WHERE id=%s"
    params.append(id)
    cursor.execute(sql, tuple(params))
    
    cursor.execute("SELECT sekcja, produkt, data_planu, tonaz FROM plan_produkcji WHERE id=%s", (id,))
    z = cursor.fetchone()
    if z and z[0] == 'Zasyp' and rzeczywista_waga > 0:
        cursor.execute("UPDATE plan_produkcji SET tonaz=%s WHERE data_planu=%s AND produkt=%s AND tonaz=%s AND sekcja='Workowanie' AND status != 'zakonczone' LIMIT 1", (rzeczywista_waga, z[2], z[1], z[3]))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/zapisz_wyjasnienie/<int:id>', methods=['POST'])
@login_required
def zapisz_wyjasnienie(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET wyjasnienie_rozbieznosci=%s WHERE id=%s", (request.form.get('wyjasnienie'), id))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


# Modal-like page endpoints for in-page slide-over usage
@api_bp.route('/koniec_zlecenie_page/<int:id>', methods=['GET'])
@login_required
def koniec_zlecenie_page(id):
    # Render a small form that posts to existing /koniec_zlecenie/<id>
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Zasyp'))
    return render_template('koniec_zlecenie.html', id=id, sekcja=sekcja)


@api_bp.route('/szarza_page/<int:plan_id>', methods=['GET'])
@login_required
def szarza_page(plan_id):
    # Render a simple form to add a szarża (delegates to dodaj_palete POST)
    return render_template('szarza.html', plan_id=plan_id)


@api_bp.route('/wyjasnij_page/<int:id>', methods=['GET'])
@login_required
def wyjasnij_page(id):
    # Render form to submit wyjasnienie via zapisz_wyjasnienie
    return render_template('wyjasnij.html', id=id)


@api_bp.route('/obsada_page', methods=['GET'])
@login_required
def obsada_page():
    """Render small slide-over for managing `obsada` (workers on shift) for a sekcja."""
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Workowanie'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # current obsada for today and given sekcja
        cursor.execute("SELECT p.id, p.imie_nazwisko FROM pracownicy p JOIN obsada_zmiany o ON o.pracownik_id=p.id WHERE o.data_wpisu=%s AND o.sekcja=%s ORDER BY p.imie_nazwisko", (date.today(), sekcja))
        obecna = cursor.fetchall()
        # available employees
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        wszyscy = cursor.fetchall()
    finally:
        try: conn.close()
        except Exception: pass

    return render_template('obsada.html', sekcja=sekcja, obsada=obecna, pracownicy=wszyscy, rola=session.get('rola'))

# ================= PALETY =================

@api_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_app.logger.info('API dodaj_palete called plan_id=%s form=%s remote=%s', plan_id, dict(request.form), request.remote_addr)
    except Exception:
        pass
    try:
        waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
    except Exception:
        waga_input = 0
    typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
    src_sekcja = request.form.get('sekcja', '')
    
    # Ensure `status` column exists (backfill default 'do_przyjecia' for new palety)
    try:
        cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN status VARCHAR(32) DEFAULT 'do_przyjecia'")
        conn.commit()
    except Exception:
        # ignore if column already exists or ALTER not permitted
        try:
            conn.rollback()
        except Exception:
            pass

    # If paleta is added from Workowanie, treat it as unconfirmed by default (status='do_przyjecia').
    # But if Workowanie provided a weight, persist it (so Magazyn can see and adjust) while still
    # requiring explicit confirmation.
    from datetime import datetime as _dt
    now_ts = _dt.now()
    # track whether we fetched an existing recent row or inserted a new one
    existing = None
    inserted_id = None
    try:
        current_app.logger.info('dodaj_palete: plan_id=%s waga_input=%s src_sekcja=%s typ=%s', plan_id, waga_input, src_sekcja, typ)
    except Exception:
        pass
    if typ == 'bigbag':
        cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, 0, %s, 0, %s, 'do_przyjecia')", (plan_id, waga_input, now_ts))
    else:
        # Server-side debounce: if a very recent paleta for same plan with same weight exists,
        # avoid inserting duplicate (protect against double-clicks / slow clients).
        try:
            # Debounce window: 15 seconds. Use tolerance for weight comparison (±2 kg)
            # Only debounce unconfirmed palety (status='do_przyjecia'), ignore confirmed ones
            tolerance = 2
            cursor.execute(
                "SELECT id, data_dodania, COALESCE(status,'') FROM palety_workowanie WHERE plan_id=%s AND ABS(COALESCE(waga,0) - %s) <= %s AND COALESCE(tara,25)=25 AND COALESCE(waga_brutto,0)=0 AND COALESCE(status,'') = 'do_przyjecia' ORDER BY id DESC LIMIT 1",
                (plan_id, waga_input, tolerance)
            )
            dup_row = cursor.fetchone()
            dup = None
            if dup_row:
                dup_id, dup_ts, dup_status = dup_row[0], dup_row[1], dup_row[2]
                # Check if within 15 second debounce window (comparing as Python datetime)
                from datetime import datetime, timedelta
                if isinstance(dup_ts, str):
                    try:
                        dup_dt = datetime.fromisoformat(dup_ts.replace('Z', '+00:00')) if 'T' in dup_ts else datetime.strptime(dup_ts, '%Y-%m-%d %H:%M:%S')
                    except:
                        dup_dt = None
                else:
                    dup_dt = dup_ts
                
                now_dt = datetime.fromisoformat(now_ts.isoformat()) if hasattr(now_ts, 'isoformat') else now_ts
                if dup_dt and (now_dt - dup_dt).total_seconds() < 15:
                    dup = (dup_id,)
            
            if dup:
                try:
                    current_app.logger.info('Skipping duplicate paleta insert for plan_id=%s waga=%s (recent id=%s)', plan_id, waga_input, dup[0])
                except Exception:
                    pass
                try:
                    cursor.execute("SELECT id, plan_id, waga, tara, waga_brutto, data_dodania, COALESCE(status,'') FROM palety_workowanie WHERE id=%s", (dup[0],))
                    existing = cursor.fetchone()
                except Exception:
                    existing = None
            else:
                if src_sekcja == 'Workowanie':
                    # Workowanie: MUST have weight (waga > 0) to be added as paleta
                    if waga_input > 0:
                        cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia')", (plan_id, waga_input, now_ts))
                        try:
                            inserted_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
                        except Exception:
                            inserted_id = None
                    else:
                        # Reject paleta with 0 weight from Workowanie
                        try:
                            current_app.logger.warning('REJECTED: Cannot add paleta with 0 weight from Workowanie (plan_id=%s). Use Zasyp for batches without weight.', plan_id)
                        except Exception:
                            pass
                        return ("Błąd: Paleta musi mieć wagę > 0. Użyj Zasyp do dodawania szarż bez wagi.", 400)
                else:
                    # Zasyp/other: MUST also have weight (waga > 0) - no 0kg batches allowed
                    if waga_input > 0:
                        cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia')", (plan_id, waga_input, now_ts))
                        try:
                            inserted_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
                        except Exception:
                            inserted_id = None
                    else:
                        # Reject batch with 0 weight from Zasyp
                        try:
                            current_app.logger.warning('REJECTED: Cannot add batch with 0 weight from Zasyp (plan_id=%s). All items must have weight > 0.', plan_id)
                        except Exception:
                            pass
                        return ("Błąd: Waga musi być > 0. Wszystkie przedmioty muszą mieć przydzieloną wagę.", 400)
        except Exception:
            # Fallback to original behavior on unexpected DB error
            try:
                if src_sekcja == 'Workowanie':
                    cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, 0, 25, 0, %s, 'do_przyjecia')", (plan_id, now_ts))
                else:
                    cursor.execute("INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia')", (plan_id, waga_input, now_ts))
            except Exception:
                try:
                    current_app.logger.exception('Failed fallback insert for paleta plan_id=%s', plan_id)
                except Exception:
                    pass
    # Log the resulting row for debugging. If we detected a recent duplicate, log that row;
    # if we inserted a new row, fetch and log the new row.
    try:
        result_row = None
        try:
            if existing:
                result_row = existing
            elif inserted_id:
                cursor.execute("SELECT id, plan_id, waga, tara, waga_brutto, data_dodania, COALESCE(status, '') FROM palety_workowanie WHERE id=%s", (inserted_id,))
                result_row = cursor.fetchone()
            else:
                # fallback: try LAST_INSERT_ID but only as last resort
                try:
                    cursor.execute("SELECT id, plan_id, waga, tara, waga_brutto, data_dodania, COALESCE(status, '') FROM palety_workowanie WHERE id = LAST_INSERT_ID()")
                    result_row = cursor.fetchone()
                except Exception:
                    result_row = None
        except Exception:
            result_row = None
        try:
            if result_row:
                current_app.logger.info('Inserted/Existing paleta row: %s', result_row)
            else:
                current_app.logger.warning('No paleta row available to log after dodaj_palete for plan_id=%s', plan_id)
        except Exception:
            pass
    except Exception:
        try:
            current_app.logger.exception('Unexpected error while logging paleta result')
        except Exception:
            pass
    
    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
    # Only sync to Magazyn if paleta from Workowanie with weight (NOT from Zasyp!)
    try:
        current_app.logger.info('Magazyn sync check: src_sekcja=%s waga_input=%s (only sync if Workowanie AND waga > 0)', src_sekcja, waga_input)
    except Exception:
        pass
    if src_sekcja == 'Workowanie' and waga_input > 0:
        try:
            current_app.logger.info('✓ Syncing to Magazyn: src_sekcja=%s waga=%s, proceeding with insert/update', src_sekcja, waga_input)
        except Exception:
            pass
        cursor.execute("SELECT data_planu, produkt, tonaz, typ_produkcji FROM plan_produkcji WHERE id=%s", (plan_id,))
        z = cursor.fetchone()
        if z:
            cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' AND typ_produkcji=%s AND status != 'zakonczone' LIMIT 1", (z[0], z[1], z[3]))
            istniejace = cursor.fetchone()
            if not istniejace: 
                try:
                    current_app.logger.info('Inserting NEW plan to Magazyn: data_planu=%s produkt=%s', z[0], z[1])
                except Exception:
                    pass
                cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji) VALUES (%s, 'Magazyn', %s, %s, 'zaplanowane', 999, %s)", (z[0], z[1], z[2], z[3]))
            else: 
                try:
                    current_app.logger.info('Updating existing plan in Magazyn: plan_id=%s', istniejace[0])
                except Exception:
                    pass
                cursor.execute("UPDATE plan_produkcji SET tonaz=%s WHERE id=%s", (z[2], istniejace[0]))
    else:
        try:
            if src_sekcja != 'Workowanie':
                current_app.logger.info('⊘ SKIPPING Magazyn sync: src_sekcja=%s (only Workowanie should sync to Magazyn)', src_sekcja)
            else:
                current_app.logger.info('⊘ SKIPPING Magazyn sync: waga_input=%s <= 0 (needs weight)', waga_input)
        except Exception:
            pass
    conn.commit()
    conn.close()
    # Nie ustawiamy parametru `open_stop` tutaj — unikamy automatycznego
    # otwierania modalu STOP po dodaniu palety/szarży.
    return redirect(bezpieczny_powrot())


@api_bp.route('/dodaj_palete_page/<int:plan_id>', methods=['GET'])
@login_required
def dodaj_palete_page(plan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    produkt = None
    sekcja = None
    typ = None
    try:
        cursor.execute("SELECT produkt, sekcja, typ_produkcji FROM plan_produkcji WHERE id=%s", (plan_id,))
        row = cursor.fetchone()
        if row:
            produkt, sekcja, typ = row[0], row[1], row[2]
    except Exception:
        try: current_app.logger.exception('Failed to fetch plan %s for dodaj_palete_page', plan_id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass
    return render_template('dodaj_palete.html', plan_id=plan_id, produkt=produkt, sekcja=sekcja, typ=typ)


@api_bp.route('/edytuj_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def edytuj_palete_page(paleta_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    waga = None
    sekcja = None
    try:
        cursor.execute("SELECT waga, plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        if row:
            waga = row[0]
            plan_id = row[1]
            cursor.execute("SELECT sekcja FROM plan_produkcji WHERE id=%s", (plan_id,))
            r2 = cursor.fetchone()
            if r2:
                sekcja = r2[0]
    except Exception:
        try: current_app.logger.exception('Failed to load paleta %s for edit page', paleta_id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass
    return render_template('edytuj_palete.html', paleta_id=paleta_id, waga=waga, sekcja=sekcja)



@api_bp.route('/confirm_delete_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def confirm_delete_palete_page(paleta_id):
    return render_template('confirm_delete_palete.html', paleta_id=paleta_id)


@api_bp.route('/potwierdz_palete_page/<int:paleta_id>', methods=['GET'])
@login_required
def potwierdz_palete_page(paleta_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    waga = None
    try:
        cursor.execute("SELECT waga, waga_brutto, tara FROM palety_workowanie WHERE id=%s", (paleta_id,))
        row = cursor.fetchone()
        if row:
            waga = row[0]
            # provide other values to template if needed later
    except Exception:
        try: current_app.logger.exception('Failed to load paleta %s for potwierdz_palete_page', paleta_id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass
    return render_template('potwierdz_palete.html', paleta_id=paleta_id, waga=waga)


@api_bp.route('/potwierdz_palete/<int:paleta_id>', methods=['POST'])
@login_required
def potwierdz_palete(paleta_id):
    # Pozwala magazynierowi (lub lider/admin) potwierdzić przyjęcie palety
    role = session.get('rola', '')
    if role not in ['magazynier', 'lider', 'admin']:
        return ("Brak uprawnień", 403)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # ensure column exists
        try:
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN status VARCHAR(32) DEFAULT 'do_przyjecia'")
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass

        # Optional: allow providing weight at confirmation time.
        try:
            # fetch tara for brutto->netto conversion (fallback to 25 if not present)
            cursor.execute("SELECT COALESCE(tara,25) FROM palety_workowanie WHERE id=%s", (paleta_id,))
            trow = cursor.fetchone()
            tara = int(trow[0]) if trow and trow[0] is not None else 25
        except Exception:
            tara = 25

        try:
            # prefer explicit netto 'waga_palety' if provided
            if request.form.get('waga_palety'):
                try:
                    from utils.validation import require_field
                    waga_input = int(float(require_field(request.form, 'waga_palety').replace(',', '.')))
                except Exception:
                    waga_input = None
                if waga_input is not None:
                    cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (waga_input, paleta_id))
                    conn.commit()
            # or accept brutto and compute netto
            elif request.form.get('waga_brutto'):
                try:
                    from utils.validation import require_field
                    brutto = int(float(require_field(request.form, 'waga_brutto').replace(',', '.')))
                except Exception:
                    brutto = 0
                netto = brutto - int(tara)
                if netto < 0: netto = 0
                cursor.execute("UPDATE palety_workowanie SET waga_brutto=%s, waga=%s WHERE id=%s", (brutto, netto, paleta_id))
                conn.commit()
        except Exception:
            try: current_app.logger.exception('Failed to set weight during potwierdz_palete for id=%s', paleta_id)
            except Exception: pass

        # Zapisz status przyjęcia oraz znacznik czasu i gotowy czas w sekundach
        try:
            cursor.execute("UPDATE palety_workowanie SET status='przyjeta', data_potwierdzenia=NOW(), czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()) WHERE id=%s", (paleta_id,))
            conn.commit()
        except Exception:
            # Fallback: jeśli ALTER nie było wykonane, ustaw tylko status
            try:
                cursor.execute("UPDATE palety_workowanie SET status='przyjeta' WHERE id=%s", (paleta_id,))
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
        try:
            # Log resulting row for debugging (status/data_potwierdzenia)
            cursor.execute("SELECT id, COALESCE(status,''), data_potwierdzenia, czas_potwierdzenia_s FROM palety_workowanie WHERE id=%s", (paleta_id,))
            res = cursor.fetchone()
            current_app.logger.info('potwierdz_palete result: %s', res)
        except Exception:
            try:
                current_app.logger.exception('Failed to fetch potwierdz_palete result for id=%s', paleta_id)
            except Exception:
                pass
        try:
            # Update plan aggregates: ensure plan's actual tonnage reflects accepted palety
            cursor.execute("SELECT plan_id, COALESCE(waga,0) FROM palety_workowanie WHERE id=%s", (paleta_id,))
            r = cursor.fetchone()
            if r:
                plan_id = r[0]
                netto_val = int(r[1] or 0)
                # Recompute total for the plan
                try:
                    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
                # Also increment aggregate for same date/product in Magazyn section (if applicable)
                try:
                    cursor.execute("SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
                    z = cursor.fetchone()
                    if z:
                        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = tonaz_rzeczywisty + %s WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'", (netto_val, z[0], z[1]))
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
                conn.commit()
        except Exception:
            try:
                current_app.logger.exception('Failed to update plan aggregates after potwierdz_palete %s', paleta_id)
            except Exception:
                pass
    except Exception:
        current_app.logger.exception('Failed to potwierdz palete %s', paleta_id)
    finally:
        try: conn.close()
        except Exception: pass
    # If request originated from AJAX (fetch), return 204 No Content so client can handle without redirect
    try:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return ('', 204)
    except Exception:
        pass
    return redirect(bezpieczny_powrot())


@api_bp.route('/telemetry/openmodal', methods=['POST'])
def telemetry_openmodal():
    try:
        data = request.get_json(silent=True) or {}
        current_app.logger.info('Telemetry openmodal: %s from %s', data, request.remote_addr)
    except Exception:
        try:
            current_app.logger.exception('Failed to log telemetry openmodal')
        except Exception:
            pass
    return ('', 204)

@api_bp.route('/wazenie_magazyn/<int:paleta_id>', methods=['POST'])
@login_required
def wazenie_magazyn(paleta_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        brutto = int(float(request.form.get('waga_brutto', '0').replace(',', '.')))
    except Exception:
        brutto = 0
    cursor.execute("SELECT tara, plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
    res = cursor.fetchone()
    if res:
        tara, plan_id = res
        netto = brutto - int(tara)
        if netto < 0: netto = 0
        cursor.execute("UPDATE palety_workowanie SET waga_brutto=%s, waga=%s WHERE id=%s", (brutto, netto, paleta_id))
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
        cursor.execute("SELECT data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
        z = cursor.fetchone()
        if z: cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = tonaz_rzeczywisty + %s WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'", (netto, z[0], z[1]))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/usun_palete/<int:id>', methods=['POST'])
@api_bp.route('/usun_palete/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def usun_palete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan_id FROM palety_workowanie WHERE id=%s", (id,))
    res = cursor.fetchone()
    if res:
        plan_id = res[0]
        cursor.execute("DELETE FROM palety_workowanie WHERE id=%s", (id,))
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
        conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@api_bp.route('/edytuj_palete/<int:paleta_id>', methods=['POST'])
@roles_required('lider', 'admin')
def edytuj_palete(paleta_id):
    """Pozwala liderowi/adminowi zmienić wagę palety (netto)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Akceptujemy pole 'waga_palety' z formularza
        try:
            waga = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
        except Exception:
            waga = 0
        # Zaktualizuj wagę palety
        cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (waga, paleta_id))
        # Zaktualizuj sumę w plan_produkcji
        cursor.execute("SELECT plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
        res = cursor.fetchone()
        if res:
            plan_id = res[0]
            cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s) WHERE id = %s", (plan_id, plan_id))
        conn.commit()
    except Exception:
        current_app.logger.exception('Failed to edit paleta %s', paleta_id)
    finally:
        try: conn.close()
        except Exception: pass
    return redirect(bezpieczny_powrot())

# ================= ZARZĄDZANIE (ZABEZPIECZONE) =================

@api_bp.route('/przywroc_zlecenie/<int:id>', methods=['POST'])
@roles_required('lider', 'admin')
def przywroc_zlecenie(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sekcja FROM plan_produkcji WHERE id=%s", (id,))
    res = cursor.fetchone()
    if res:
        cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (res[0],))
        cursor.execute("UPDATE plan_produkcji SET status='w toku', real_stop=NULL WHERE id=%s", (id,))
        conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/zmien_status_zlecenia/<int:id>', methods=['POST'])
@login_required
def zmien_status_zlecenia(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    from utils.validation import require_field
    status = require_field(request.form, 'status')
    cursor.execute("UPDATE plan_produkcji SET status=%s WHERE id=%s", (status, id))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def usun_plan(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    redirect_target = bezpieczny_powrot()
    category = None
    message = None
    try:
        cursor.execute("SELECT status FROM plan_produkcji WHERE id=%s", (id,))
        res = cursor.fetchone()
        if not res:
            category, message = 'warning', 'Zlecenie nie istnieje.'
        elif res[0] in ['w toku', 'zakonczone']:
            category, message = 'warning', 'Nie można usunąć zleczenia w toku lub już zakończonego.'
        else:
            cursor.execute("DELETE FROM palety_workowanie WHERE plan_id=%s", (id,))
            cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (id,))
            conn.commit()
            category, message = 'success', 'Zlecenie zostało usunięte z planu.'
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Failed to delete plan %s', id)
        category, message = 'error', 'Wystąpił błąd przy usuwaniu zlecenia. Sprawdź logi.'
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if category and message:
        flash(message, category)
    return redirect(redirect_target)

@api_bp.route('/dodaj_plan_zaawansowany', methods=['POST'])
@roles_required('planista', 'admin')
def dodaj_plan_zaawansowany():
    sekcja = request.form.get('sekcja')
    data_planu = request.form.get('data_planu')
    from utils.validation import require_field
    produkt = require_field(request.form, 'produkt')
    typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
    status = 'nieoplacone' if request.form.get('wymaga_oplaty') else 'zaplanowane'
    try:
        tonaz = int(float(require_field(request.form, 'tonaz')))
    except Exception:
        tonaz = 0
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) VALUES (%s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, status, sekcja, nk, typ))
    conn.commit()
    conn.close()
    return redirect(url_for('planista.panel_planisty', data=data_planu))


@api_bp.route('/dodaj_plan', methods=['POST'])
@roles_required('planista', 'admin')
def dodaj_plan():
    # Backwards-compatible simple add used by small section widgets
    data_planu = request.form.get('data_planu') or request.form.get('data') or str(date.today())
    from utils.validation import require_field
    produkt = require_field(request.form, 'produkt')
    try:
        tonaz = int(float(request.form.get('tonaz', 0)))
    except Exception:
        tonaz = 0
    sekcja = request.form.get('sekcja') or request.args.get('sekcja') or 'Nieprzydzielony'
    status = 'zaplanowane'
    typ = request.form.get('typ_produkcji', 'worki_zgrzewane_25')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) VALUES (%s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, status, sekcja, nk, typ))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@api_bp.route('/planista/bulk', methods=['GET'])
@roles_required('planista', 'admin')
def planista_bulk_page():
    # Render a larger page for planista to add multiple plans then confirm
    wybrana_data = request.args.get('data', str(date.today()))
    return render_template('planista_bulk.html', wybrana_data=wybrana_data)


@api_bp.route('/dodaj_plany_batch', methods=['POST'])
@roles_required('planista', 'admin')
def dodaj_plany_batch():
    # Accept JSON payload with data_planu and list of plan objects
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
        # Compute initial max kolejność
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
            cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', sekcja, nk, typ, nr))
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

@api_bp.route('/przenies_zlecenie/<int:id>', methods=['POST'])
@login_required
def przenies_zlecenie(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # BLOKADA: Sprawdź status przed zmianą daty
    cursor.execute("SELECT status FROM plan_produkcji WHERE id=%s", (id,))
    res = cursor.fetchone()
    if res and res[0] in ['w toku', 'zakonczone']:
        conn.close()
        return redirect(bezpieczny_powrot())

    nd = request.form.get('nowa_data')
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (nd,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("UPDATE plan_produkcji SET data_planu=%s, kolejnosc=%s WHERE id=%s", (nd, nk, id))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


# Endpoint '/przenies_do_jakosc' usunięty — dezynfekcja jest planowana przez laboratorium
# i zgłaszana planiście; nie używamy już serwerowego mechanizmu "przenieś do Jakość".


@api_bp.route('/przesun_zlecenie/<int:id>/<kierunek>', methods=['POST'])
@roles_required('planista', 'admin')
def przesun_zlecenie(id, kierunek):
    data = request.args.get('data', str(date.today()))
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # BLOKADA: Sprawdź status przed przesunięciem
    cursor.execute("SELECT id, kolejnosc, status FROM plan_produkcji WHERE id=%s", (id,))
    obecne = cursor.fetchone()
    
    if obecne and obecne[2] not in ['w toku', 'zakonczone']:
        oid, okol, _ = obecne
        q = "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc < %s ORDER BY kolejnosc DESC LIMIT 1" if kierunek == 'gora' else "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc > %s ORDER BY kolejnosc ASC LIMIT 1"
        cursor.execute(q, (data, okol))
        sasiad = cursor.fetchone()
        if sasiad:
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (sasiad[1], oid))
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (okol, sasiad[0]))
            conn.commit()
            
    conn.close()
    return redirect(url_for('planista.panel_planisty', data=data))


# ================= JAKOŚĆ -> DODAJ DO PLANÓW =================
@api_bp.route('/jakosc/dodaj_do_planow/<int:id>', methods=['POST'])
@roles_required('planista', 'admin')
def jakosc_dodaj_do_planow(id):
    """Utwórz zaplanowane zlecenie produkcyjne na podstawie zlecenia jakościowego."""
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
    # Oblicz nową kolejność
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) VALUES (%s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', 'Zasyp', nk, typ))
    conn.commit()
    conn.close()
    flash('Zlecenie dodane do planów', 'success')
    return redirect(bezpieczny_powrot())

# ================= DZIENNIK =================

@api_bp.route('/dodaj_wpis', methods=['POST'])
@login_required
def dodaj_wpis():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from utils.validation import require_field, optional_field
        sekcja = require_field(request.form, 'sekcja')
        kategoria = require_field(request.form, 'kategoria')
        problem = optional_field(request.form, 'problem', default=None)
        czas_start = optional_field(request.form, 'czas_start', default=None)
    except Exception as e:
        from flask import flash
        flash(str(e), 'danger')
        conn.close()
        return redirect(bezpieczny_powrot())
    cursor.execute("INSERT INTO dziennik_zmiany (data_wpisu, sekcja, problem, czas_start, status, kategoria) VALUES (%s, %s, %s, %s, 'roboczy', %s)", (date.today(), sekcja, problem, czas_start, kategoria))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/usun_wpis/<int:id>', methods=['POST'])
@login_required
def usun_wpis(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dziennik_zmiany WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/edytuj/<int:id>', methods=['GET', 'POST'])
@login_required
def edytuj(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'POST':
            # If no end time provided when editing, set end time to now (click time)
            czas_start_val = request.form.get('czas_start') or None
            czas_stop_form = request.form.get('czas_stop')
            if czas_stop_form:
                czas_stop_val = czas_stop_form
            else:
                # set to current datetime — DB column accepts time/datetime
                from datetime import datetime as _dt
                czas_stop_val = _dt.now()

            cursor.execute(
                "UPDATE dziennik_zmiany SET problem=%s, kategoria=%s, czas_start=%s, czas_stop=%s WHERE id=%s",
                (request.form.get('problem'), request.form.get('kategoria'), czas_start_val, czas_stop_val, id)
            )
            conn.commit()
            conn.close()
            return redirect('/')

        cursor.execute("SELECT * FROM dziennik_zmiany WHERE id = %s", (id,))
        wpis = cursor.fetchone()
        if not wpis:
            # brak wpisu — przyjazne przekierowanie
            conn.close()
            from flask import flash
            flash('Wpis nie został odnaleziony.', 'warning')
            return redirect(bezpieczny_powrot())

        # Format time fields for the template (HH:MM). db may return timedelta or datetime
        wpis_display = list(wpis)
        for ti in (6, 7):
            try:
                val = wpis[ti]
                if val is None:
                    wpis_display[ti] = ''
                elif isinstance(val, datetime):
                    wpis_display[ti] = val.strftime('%H:%M')
                elif isinstance(val, time):
                    wpis_display[ti] = val.strftime('%H:%M')
                elif isinstance(val, timedelta):
                    total_seconds = int(val.total_seconds())
                    h = total_seconds // 3600
                    m = (total_seconds % 3600) // 60
                    wpis_display[ti] = f"{h:02d}:{m:02d}"
                else:
                    # fallback to string, try to extract HH:MM
                    s = str(val)
                    if ':' in s:
                        parts = s.split(':')
                        wpis_display[ti] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    else:
                        wpis_display[ti] = s
            except Exception:
                wpis_display[ti] = ''

        conn.close()
        return render_template('edycja.html', wpis=wpis_display)
    except Exception:
        # Zaloguj i pokaż przyjazny komunikat zamiast 500
        app = None
        try:
            from flask import current_app
            app = current_app._get_current_object()
            app.logger.exception('Error in edytuj endpoint for id=%s', id)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        from flask import flash
        flash('Wystąpił błąd podczas ładowania wpisu.', 'danger')


# Ręczne wyzwalanie przypomnień dla niepotwierdzonych palet
@api_bp.route('/remind_unconfirmed_palety', methods=['POST'])
@roles_required('lider', 'admin')
def remind_unconfirmed_palety():
    try:
        try:
            threshold = int(request.form.get('threshold_minutes', 10))
        except Exception:
            threshold = 10
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.waga = 0 AND TIMESTAMPDIFF(MINUTE, pw.data_dodania, NOW()) >= %s",
            (threshold,)
        )
        raw = cursor.fetchall()
        rows = []
        for r in raw:
            # map tuple (id, plan_id, produkt, data_dodania) explicitly
            dto = PaletaDTO.from_db_row(r, columns=('id', 'plan_id', 'produkt', 'data_dodania'))
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            rows.append((dto.id, dto.plan_id, dto.produkt, sdt))
        conn.close()

        palety_logger = logging.getLogger('palety_logger')
        count = 0
        for r in rows:
            msg = f"Manual reminder: Niepotwierdzona paleta id={r[0]}, plan_id={r[1]}, produkt={r[2]}, dodana={r[3]} - brak potwierdzenia >= {threshold}min"
            palety_logger.warning(msg)
            try:
                current_app.logger.warning(msg)
            except Exception:
                pass
            count += 1

        # Jeśli żądanie JSON, zwróć JSON, inaczej przekieruj z komunikatem
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'reminded': count})
        flash(f'Wysłano przypomnienia dla {count} palet.', 'info')
        return redirect(bezpieczny_powrot())
    except Exception:
        current_app.logger.exception('Error in remind_unconfirmed_palety')
        flash('Wystąpił błąd podczas wysyłania przypomnień.', 'danger')
        return redirect(bezpieczny_powrot())
        return redirect(bezpieczny_powrot())


@api_bp.route('/ustawienia', methods=['GET'])
@login_required
def ustawienia():
    """Prosty widok ustawień (placeholder)."""
    try:
        return render_template('ustawienia.html')
    except Exception:
        from flask import flash
        flash('Nie można otworzyć strony ustawień.', 'danger')
        return redirect('/')

@api_bp.route('/zapisz_tonaz_deprecated/<int:id>', methods=['POST'])
def zapisz_tonaz_deprecated(id): return redirect(bezpieczny_powrot())

# ================= OBSADA I INNE =================
@api_bp.route('/dodaj_obecnosc', methods=['POST'])
@login_required
def dodaj_obecnosc():
    conn = get_db_connection()
    cursor = conn.cursor()
    typ = request.form.get('typ')
    pracownik_id = request.form.get('pracownik_id')
    godziny = request.form.get('godziny', 0)
    try:
        godziny_val = float(str(godziny).replace(',', '.'))
    except Exception:
        godziny_val = 0.0
    komentarz = request.form.get('komentarz', '')
    # Server-side: walidacja wymaganych pól i czytelny komunikat
    missing = []
    if not pracownik_id:
        missing.append('Pracownik')
    if not typ:
        missing.append('Typ')
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        if not od: missing.append('Czas (od)')
        if not do: missing.append('Czas (do)')
    if missing:
        try:
            flash('Brakuje wymaganych pól: ' + ', '.join(missing), 'warning')
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return redirect(bezpieczny_powrot())
    # Jeśli Wyjscie prywatne — wymagamy podania zakresu czasu
    od = None
    do = None
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        # Dołączamy zakres czasowy do komentarza dla zapisu (kompatybilność wsteczna)
        komentarz = f"Wyjście prywatne od {od} do {do}" + (f" — {komentarz}" if komentarz else '')

    # Zapisz też osobne kolumny wyjscie_od/wyjscie_do (mogą być NULL jeśli nie dotyczy)
    cursor.execute(
        "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz, wyjscie_od, wyjscie_do) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (date.today(), pracownik_id, typ, godziny_val, komentarz, od, do)
    )
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@api_bp.route('/edytuj_godziny', methods=['POST'])
@login_required
def edytuj_godziny():
    """Edytuj/liczba godzin dla danego pracownika i daty (AJAX)."""
    try:
        pracownik_id = request.form.get('pracownik_id') or request.args.get('pracownik_id')
        date_str = request.form.get('date') or request.args.get('date')
        from utils.validation import require_field
        godziny = require_field(request.form, 'godziny')
        if not pracownik_id or not date_str:
            return jsonify({'success': False, 'message': 'Brak parametrów'}), 400
        try:
            pid = int(pracownik_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowy pracownik'}), 400

        # Uprawnienia: właściciel może edytować swoje godziny, lider/admin może edytować inne
        try:
            my_pid = session.get('pracownik_id')
            my_role = (session.get('rola') or '').lower()
        except Exception:
            my_pid = None; my_role = ''
        if my_pid != pid and my_role not in ('lider', 'admin'):
            return jsonify({'success': False, 'message': 'Brak uprawnień'}), 403

        try:
            hours_val = float(str(godziny).replace(',', '.'))
        except Exception:
            hours_val = 0.0

        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy istnieje wiersz obecnosc dla tej daty i pracownika
        cursor.execute("SELECT id FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s LIMIT 1", (pid, date_str))
        res = cursor.fetchone()
        if res:
            cursor.execute("UPDATE obecnosc SET ilosc_godzin=%s WHERE id=%s", (hours_val, res[0]))
        else:
            cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (date_str, pid, 'Obecność', hours_val, 'Edytowano ręcznie'))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Godziny zapisane'})
    except Exception:
        current_app.logger.exception('Error editing hours')
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500


# =============== WNIOSKI O WOLNE ================
@api_bp.route('/wnioski/submit', methods=['POST'])
@login_required
def submit_wniosek():
    conn = get_db_connection()
    cursor = conn.cursor()
    pid = session.get('pracownik_id') or request.form.get('pracownik_id')
    if not pid:
        try:
            flash('Brak przypisanego pracownika do konta. Skontaktuj się z administratorem.', 'warning')
        except Exception:
            pass
        return redirect(bezpieczny_powrot())

    typ = request.form.get('typ') or 'Urlop'
    data_od = request.form.get('data_od')
    data_do = request.form.get('data_do')
    czas_od = request.form.get('czas_od') or None
    czas_do = request.form.get('czas_do') or None
    powod = request.form.get('powod') or ''

    # Jeśli to Wyjście prywatne — akceptujemy również pojedynczy dzień (data_do może być pusta)
    if typ and typ.lower().startswith('wyj'):
        if not data_od:
            try:
                flash('Podaj datę wniosku.', 'warning')
            except Exception:
                pass
            return redirect(bezpieczny_powrot())
        # jeśli brak data_do, ustawiamy na tę samą datę (pojedynczy dzień z godzinami)
        if not data_do:
            data_do = data_od
    else:
        if not data_od or not data_do:
            try:
                flash('Podaj zakres dat wniosku.', 'warning')
            except Exception:
                pass
            return redirect(bezpieczny_powrot())

    cursor.execute("INSERT INTO wnioski_wolne (pracownik_id, typ, data_od, data_do, czas_od, czas_do, powod) VALUES (%s, %s, %s, %s, %s, %s, %s)", (pid, typ, data_od, data_do, czas_od, czas_do, powod))
    conn.commit()
    conn.close()
    try:
        flash('Wniosek złożony pomyślnie.', 'success')
    except Exception:
        pass
    return redirect(url_for('moje_godziny'))


@api_bp.route('/wnioski/<int:wid>/approve', methods=['POST'])
@roles_required('lider', 'admin')
def approve_wniosek(wid):
    conn = get_db_connection()
    cursor = conn.cursor()
    lider_pid = session.get('pracownik_id')
    cursor.execute("UPDATE wnioski_wolne SET status='approved', decyzja_dnia=NOW(), lider_id=%s WHERE id=%s", (lider_pid, wid))
    conn.commit()
    # After approving, increment employee's leave counters by number of days in the request
    try:
        cursor.execute("SELECT pracownik_id, data_od, data_do, typ FROM wnioski_wolne WHERE id=%s", (wid,))
        r = cursor.fetchone()
        if r:
            pid = int(r[0])
            data_od = r[1]
            data_do = r[2]
            typ = (r[3] or '').lower()
            # compute inclusive days
            try:
                days = (data_do - data_od).days + 1 if (data_od and data_do) else 0
            except Exception:
                days = 0
            if days > 0:
                # Ensure columns exist (best-effort)
                try:
                    cursor.execute("ALTER TABLE pracownicy ADD COLUMN IF NOT EXISTS urlop_biezacy INT DEFAULT 0")
                    cursor.execute("ALTER TABLE pracownicy ADD COLUMN IF NOT EXISTS urlop_zalegly INT DEFAULT 0")
                except Exception:
                    # some MySQL versions may not support IF NOT EXISTS; ignore errors
                    try:
                        cursor.execute("ALTER TABLE pracownicy ADD COLUMN urlop_biezacy INT DEFAULT 0")
                        cursor.execute("ALTER TABLE pracownicy ADD COLUMN urlop_zalegly INT DEFAULT 0")
                    except Exception:
                        pass
                # Decide which counter to increment — default to current-year ('urlop_biezacy')
                if 'zaleg' in typ:
                    cursor.execute("UPDATE pracownicy SET urlop_zalegly = COALESCE(urlop_zalegly,0) + %s WHERE id=%s", (days, pid))
                else:
                    cursor.execute("UPDATE pracownicy SET urlop_biezacy = COALESCE(urlop_biezacy,0) + %s WHERE id=%s", (days, pid))
                conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    conn.close()
    try:
        flash('Wniosek zatwierdzony.', 'success')
    except Exception:
        pass
    # If this is an AJAX request, return JSON instead of redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify({'success': True, 'message': 'Wniosek zatwierdzony.'})
    return redirect(bezpieczny_powrot())


@api_bp.route('/wnioski/<int:wid>/reject', methods=['POST'])
@roles_required('lider', 'admin')
def reject_wniosek(wid):
    conn = get_db_connection()
    cursor = conn.cursor()
    lider_pid = session.get('pracownik_id')
    cursor.execute("UPDATE wnioski_wolne SET status='rejected', decyzja_dnia=NOW(), lider_id=%s WHERE id=%s", (lider_pid, wid))
    conn.commit()
    conn.close()
    try:
        flash('Wniosek odrzucony.', 'info')
    except Exception:
        pass
    # If this is an AJAX request, return JSON instead of redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify({'success': True, 'message': 'Wniosek odrzucony.'})
    return redirect(bezpieczny_powrot())


@api_bp.route('/wnioski/day', methods=['GET'])
@roles_required('lider', 'admin')
def wnioski_for_day():
    """Zwraca JSON listę wniosków dla danego pracownika i daty (YYYY-MM-DD)."""
    pracownik_id = request.args.get('pracownik_id')
    date_str = request.args.get('date')
    try:
        if not pracownik_id or not date_str:
            return jsonify({'error': 'missing parameters'}), 400
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, typ, data_od, data_do, czas_od, czas_do, powod, status, zlozono FROM wnioski_wolne WHERE pracownik_id=%s AND data_od <= %s AND data_do >= %s ORDER BY zlozono DESC", (pracownik_id, date_str, date_str))
        rows = cursor.fetchall()
        conn.close()
        items = []
        for r in rows:
            items.append({'id': r[0], 'typ': r[1], 'data_od': str(r[2]), 'data_do': str(r[3]), 'czas_od': str(r[4]) if r[4] else None, 'czas_do': str(r[5]) if r[5] else None, 'powod': r[6], 'status': r[7], 'zlozono': str(r[8])})
        return jsonify({'wnioski': items})
    except Exception:
        current_app.logger.exception('Error fetching wnioski for day')
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'error': 'server error'}), 500


@api_bp.route('/wnioski/summary', methods=['GET'])
@login_required
def wnioski_summary():
    """Zwraca JSON z podsumowaniem godzin dla pracownika (obecnosci, wyjscia_hours, typy)"""
    try:
        pracownik_id = request.args.get('pracownik_id') or session.get('pracownik_id')
        if not pracownik_id:
            return jsonify({'error': 'missing pracownik_id'}), 400
        try:
            pid = int(pracownik_id)
        except Exception:
            return jsonify({'error': 'invalid pracownik_id'}), 400

        # zakres: obecny miesiąc
        from datetime import datetime, date
        teraz = datetime.now()
        d_od = date(teraz.year, teraz.month, 1)
        d_do = date(teraz.year, teraz.month, teraz.day)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s", (pid, d_od, d_do))
        obecnosci = int(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COALESCE(typ, ''), COALESCE(SUM(ilosc_godzin),0) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s GROUP BY typ", (pid, d_od, d_do))
        typy = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}

        try:
            cursor.execute("SELECT COALESCE(SUM(TIME_TO_SEC(wyjscie_do)-TIME_TO_SEC(wyjscie_od))/3600,0) FROM obecnosc WHERE pracownik_id=%s AND typ='Wyjscie prywatne' AND data_wpisu BETWEEN %s AND %s", (pid, d_od, d_do))
            wyjscia_hours = float(cursor.fetchone()[0] or 0)
        except Exception:
            wyjscia_hours = 0.0

        # also include leave counters from pracownicy (if available)
        try:
            cursor.execute("SELECT COALESCE(urlop_biezacy,0), COALESCE(urlop_zalegly,0) FROM pracownicy WHERE id=%s", (pid,))
            rr = cursor.fetchone()
            urlop_biezacy = int(rr[0] or 0) if rr else 0
            urlop_zalegly = int(rr[1] or 0) if rr else 0
        except Exception:
            urlop_biezacy = 0
            urlop_zalegly = 0
        conn.close()
        return jsonify({'obecnosci': obecnosci, 'typy': typy, 'wyjscia_hours': wyjscia_hours, 'urlop_biezacy': urlop_biezacy, 'urlop_zalegly': urlop_zalegly})
    except Exception:
        current_app.logger.exception('Error building summary')
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'error': 'server error'}), 500


@api_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM obecnosc WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/dodaj_do_obsady', methods=['POST'])
@login_required
def dodaj_do_obsady():
    conn = get_db_connection()
    cursor = conn.cursor()
    sekcja = request.form.get('sekcja')
    pracownik_id = request.form.get('pracownik_id')
    if not sekcja or not pracownik_id:
        # brak wymaganych pól — nie powodujemy 500, a pokazujemy informację i wracamy
        try:
            flash('Brak wybranego pracownika lub sekcji przy dodawaniu do obsady.', 'warning')
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return redirect(bezpieczny_powrot())
    try:
        cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (date.today(), sekcja, pracownik_id))
        # Attempt to retrieve the inserted row id for AJAX clients
        try:
            cursor.execute("SELECT id FROM obsada_zmiany WHERE data_wpisu=%s AND sekcja=%s AND pracownik_id=%s ORDER BY id DESC LIMIT 1", (date.today(), sekcja, pracownik_id))
            inserted_row = cursor.fetchone()
            inserted_id = inserted_row[0] if inserted_row else None
        except Exception:
            inserted_id = None
        # Automatyczne zapisanie obecności przy dodaniu do obsady (jeśli brak już wpisu)
        try:
            default_hours = 8
            cursor.execute("SELECT COUNT(1) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, date.today()))
            exists = int(cursor.fetchone()[0] or 0)
            if not exists:
                cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (date.today(), pracownik_id, 'Obecność', default_hours, 'Automatyczne z obsady'))
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    # If called via AJAX, return JSON with inserted id so frontend can update UI without reload
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            # try to fetch worker name for convenience
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT imie_nazwisko FROM pracownicy WHERE id=%s", (pracownik_id,))
            row = cur.fetchone()
            name = row[0] if row else ''
            try: conn.close()
            except: pass
        except Exception:
            name = ''
        return jsonify({'success': True, 'id': inserted_id, 'pracownik_id': pracownik_id, 'name': name})

    return redirect(bezpieczny_powrot())

@api_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM obsada_zmiany WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())
@api_bp.route('/zamknij-zmiane', methods=['GET'])
@login_required
@roles_required(['lider', 'admin'])
def zamknij_zmiane():
    """Wyświetl stronę podsumowania i zamknięcia zmiany - KONKRETNA SEKCJA"""
    dzisiaj = date.today()
    sekcja = request.args.get('sekcja', 'Workowanie')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Pobierz dane o zmianach dzisiaj
    cursor.execute("""
        SELECT id, produkt, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji
        FROM plan_produkcji
        WHERE data_planu = %s AND sekcja = %s
        ORDER BY real_start DESC
    """, (dzisiaj, sekcja))
    
    plany = []
    for row in cursor.fetchall():
        plan_id, produkt, tonaz, status, real_start, real_stop, tonaz_wykonania, typ_prod = row
        
        # Pobierz palety
        cursor.execute("""
            SELECT id, waga, data_dodania, status, czas_potwierdzenia_s
            FROM palety_workowanie
            WHERE plan_id = %s
            ORDER BY data_dodania DESC
        """, (plan_id,))
        
        palety = []
        for p in cursor.fetchall():
            palety.append({
                'id': p[0],
                'waga': p[1],
                'data_dodania': p[2].strftime('%Y-%m-%d %H:%M:%S') if p[2] else 'N/A',
                'status': p[3],
                'czas_potwierdzenia_s': p[4]
            })
        
        plany.append({
            'id': plan_id,
            'produkt': produkt,
            'tonaz': tonaz,
            'tonaz_wykonania': tonaz_wykonania or 0,
            'status': status,
            'real_start': real_start.strftime('%H:%M:%S') if real_start else 'N/A',
            'real_stop': real_stop.strftime('%H:%M:%S') if real_stop else 'N/A',
            'typ_produkcji': typ_prod,
            'palety': palety
        })
    
    # Pobierz pracowników na zmianie
    cursor.execute("""
        SELECT DISTINCT pw.id, pw.imie_nazwisko
        FROM (
            SELECT DISTINCT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND sekcja = %s
        ) ozm
        JOIN pracownicy pw ON ozm.pracownik_id = pw.id
    """, (dzisiaj, sekcja))
    
    pracownicy = []
    for row in cursor.fetchall():
        pracownicy.append({
            'id': row[0],
            'imie': row[1]
        })
    
    # Pobierz informacje o liderze
    lider_id = session.get('pracownik_id')
    lider_name = session.get('login', 'N/A')
    
    conn.close()
    
    zmiana_data = {
        'data': dzisiaj.strftime('%Y-%m-%d'),
        'sekcja': sekcja,
        'lider_name': lider_name,
        'lider_id': lider_id,
        'plany': plany,
        'pracownicy': pracownicy,
        'notatki': ''
    }
    
    return render_template('podsumowanie_zmiany.html',
                          zmiana_data=zmiana_data,
                          sekcja=sekcja,
                          rola=session.get('rola'))

@api_bp.route('/zamknij-zmiane-global', methods=['POST', 'GET'])
@login_required
@roles_required('lider', 'admin')
def zamknij_zmiane_global():
    """Generuj raport TXT, Excel i PDF dla wszystkich sekcji.
    Akceptuje opcjonalny parametr `data` (YYYY-MM-DD) z formularza/querystring.
    """
    # domyślna data to dziś, ale pozwól podać konkretną datę z formularza
    date_str = request.values.get('data') or request.args.get('data')
    if date_str:
        try:
            dzisiaj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            dzisiaj = date.today()
    else:
        dzisiaj = date.today()
    
    print("\n" + "="*60)
    print("[ROUTE] /zamknij-zmiane-global called")
    print(f"[ROUTE] Method: {request.method}")
    print(f"[ROUTE] Date: {dzisiaj}")
    print("="*60)
    
    # Import generator
    try:
        from generator_raportow import generuj_paczke_raportow
        print("[ROUTE] ✓ Generator module imported")
    except ImportError as e:
        print(f"[ROUTE] ✗ Failed to import generator: {e}")
        flash('⚠️ Błąd: Nie można załadować generatora raportów', 'error')
        return redirect('/')
    
    # Pobierz notatki zmianowe (shift_notes) dla dzisiejszego dnia
    uwagi = ""
    try:
        conn_notes = get_db_connection()
        cursor_notes = conn_notes.cursor(dictionary=True)
        
        query_notes = "SELECT note, author, created FROM shift_notes WHERE DATE(created) = %s ORDER BY created ASC"
        date_param = dzisiaj.strftime('%Y-%m-%d')
        print(f"[ROUTE] Executing query with date={date_param}")
        cursor_notes.execute(query_notes, (date_param,))
        notes = cursor_notes.fetchall()
        cursor_notes.close()
        conn_notes.close()
        
        print(f"[ROUTE] Query result - notes count: {len(notes)}")
        if notes:
            print(f"[ROUTE] ✓ Loaded {len(notes)} shift notes from database")
            print(f"[ROUTE] First note: {notes[0] if notes else 'N/A'}")
            # Formatuj notatki do uwagi
            uwagi = "NOTATKI ZMIANOWE:\n" + "-" * 50 + "\n"
            for i, note in enumerate(notes):
                # Formatuj czas w Pythonie
                created_time = note['created'].strftime('%H:%M:%S') if note['created'] else '??:??:??'
                uwagi += f"\n[{created_time}] {note['author']}:\n{note['note']}\n"
                print(f"[ROUTE] Note {i+1}: author={note['author']}, time={created_time}, length={len(note['note'])}")
        else:
            print(f"[ROUTE] ⚠️ No shift notes found for {date_param}")
            uwagi = ""
    except Exception as e:
        print(f"[ROUTE] ✗ Error loading shift notes: {e}")
        import traceback
        traceback.print_exc()
        uwagi = ""
    
    print(f"[ROUTE] final notatki zmianowe: length={len(uwagi)} chars")
    if uwagi:
        print(f"[ROUTE] uwagi preview (first 200 chars): {uwagi[:200]}...")
    
    try:
        # Pobierz imię i nazwisko lidera z bazy (używając pracownik_id)
        lider_name = "Nieznany"
        pracownik_id = session.get('pracownik_id')
        lider_login = session.get('login', 'nieznany')
        
        print(f"[ROUTE] Looking for lider: pracownik_id={pracownik_id}, login={lider_login}")
        
        if pracownik_id:
            try:
                conn_user = get_db_connection()
                cursor_user = conn_user.cursor(dictionary=True)
                cursor_user.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                user_data = cursor_user.fetchone()
                cursor_user.close()
                conn_user.close()
                if user_data and user_data.get('imie_nazwisko'):
                    lider_name = user_data['imie_nazwisko']
                    print(f"[ROUTE] ✓ Found lider name: {lider_name} (from pracownik_id={pracownik_id})")
                else:
                    print(f"[ROUTE] ⚠️ No imie_nazwisko found for pracownik_id={pracownik_id}")
            except Exception as e:
                print(f"[ROUTE] ✗ Error fetching lider name: {e}")
        else:
            print(f"[ROUTE] ⚠️ No pracownik_id in session, using login={lider_login}")
            lider_name = lider_login
        
        # Generuj raporty
        date_str = dzisiaj.strftime('%Y-%m-%d')
        print(f"[ROUTE] Calling generator with date={date_str}, lider={lider_name}, uwagi_len={len(uwagi)}")
        xls_path, txt_path, pdf_path = generuj_paczke_raportow(date_str, uwagi, lider_name)
        
        # Loguj sukces
        print(f"[ROUTE] ✓ Reports generated successfully!")
        print(f"[ROUTE] Excel: {xls_path}")
        print(f"[ROUTE] TXT: {txt_path}")
        print(f"[ROUTE] PDF: {pdf_path}")
        
        # Stwórz ZIP z wszystkimi plikami
        import os
        import zipfile
        from io import BytesIO
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Dodaj Excel
            if xls_path and os.path.exists(xls_path):
                zip_file.write(xls_path, arcname=os.path.basename(xls_path))
                print(f"[ROUTE] ✓ Added to ZIP: {os.path.basename(xls_path)}")
            
            # Dodaj TXT
            if txt_path and os.path.exists(txt_path):
                zip_file.write(txt_path, arcname=os.path.basename(txt_path))
                print(f"[ROUTE] ✓ Added to ZIP: {os.path.basename(txt_path)}")
            
            # Dodaj PDF
            if pdf_path and os.path.exists(pdf_path):
                zip_file.write(pdf_path, arcname=os.path.basename(pdf_path))
                print(f"[ROUTE] ✓ Added to ZIP: {os.path.basename(pdf_path)}")
        
        zip_buffer.seek(0)
        zip_filename = f"Raporty_{date_str}.zip"
        print(f"[ROUTE] ✓ ZIP created: {zip_filename}")
        print("="*60 + "\n")
        
        # Zwróć ZIP do pobrania
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        print(f"[ROUTE] ✗ Error generating reports:")
        print(f"[ROUTE] {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'❌ Błąd przy generowaniu raportów: {str(e)}', 'error')
        print("="*60 + "\n")
        return redirect('/')


@api_bp.route('/obsada-for-date')
@login_required
def obsada_for_date():
    """Zwraca listę przypisanych pracowników dla podanej daty (parametr `date` YYYY-MM-DD)."""
    date_str = request.args.get('date')
    try:
        if date_str:
            qdate = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            qdate = date.today()
    except Exception:
        qdate = date.today()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT oz.sekcja, pw.id, pw.imie_nazwisko
            FROM obsada_zmiany oz
            JOIN pracownicy pw ON oz.pracownik_id = pw.id
            WHERE oz.data_wpisu = %s
            ORDER BY oz.sekcja, pw.imie_nazwisko
        """, (qdate,))
        rows = []
        for r in cursor.fetchall():
            rows.append({'sekcja': r[0], 'id': r[1], 'imie_nazwisko': r[2]})
        conn.close()
        return jsonify({'date': qdate.isoformat(), 'rows': rows})
    except Exception as e:
        try:
            current_app.logger.exception('obsada_for_date error')
        except Exception:
            pass
        return jsonify({'date': qdate.isoformat(), 'rows': [], 'error': str(e)}), 500


@api_bp.route('/zapisz-raport-koncowy', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_raport_koncowy():
    """Zapisz raport końcowy i zamknij zmianę - KONKRETNA SEKCJA"""
    dzisiaj = date.today()
    sekcja = request.form.get('sekcja', 'Workowanie')
    notatki = request.form.get('notatki', '')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz dane zmiany
        cursor.execute("""
            SELECT id, produkt, tonaz, tonaz_rzeczywisty
            FROM plan_produkcji
            WHERE data_planu = %s AND sekcja = %s
        """, (dzisiaj, sekcja))
        
        plany_data = []
        for row in cursor.fetchall():
            plany_data.append({
                'id': row[0],
                'produkt': row[1],
                'tonaz': row[2],
                'tonaz_wykonania': row[3] or 0
            })
        
        # Pobierz pracowników
        cursor.execute("""
            SELECT pw.id, pw.imie_nazwisko
            FROM obsada_zmiany oz
            JOIN pracownicy pw ON oz.pracownik_id = pw.id
            WHERE oz.data_wpisu = %s AND oz.sekcja = %s
        """, (dzisiaj, sekcja))
        
        pracownicy_data = []
        for row in cursor.fetchall():
            pracownicy_data.append({
                'id': row[0],
                'imie': row[1]
            })
        
        lider_id = session.get('pracownik_id')
        
        # Przygotuj dane do zapisania
        zmiana_summary = {
            'data': dzisiaj.isoformat(),
            'sekcja': sekcja,
            'lider_id': lider_id,
            'plany': plany_data,
            'pracownicy': pracownicy_data,
            'notatki': notatki
        }
        
        # Zapisz raport do bazy
        import json
        cursor.execute("""
            INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json)
            VALUES (%s, %s, %s, %s, %s)
        """, (dzisiaj, sekcja, lider_id, notatki, json.dumps(zmiana_summary)))
        
        # Oznacz plany jako zamknięte
        cursor.execute("""
            UPDATE plan_produkcji
            SET status = 'zamknieta'
            WHERE data_planu = %s AND sekcja = %s AND status != 'zamknieta'
        """, (dzisiaj, sekcja))
        
        conn.commit()
        conn.close()
        
        flash(f"✅ Zmiana w sekcji {sekcja} została zamknięta!", 'success')
        return redirect(url_for('index', sekcja=sekcja, data=dzisiaj.isoformat()))
        
    except Exception as e:
        current_app.logger.error(f"Błąd przy zamykaniu zmiany: {e}")
        flash(f"❌ Błąd: {str(e)}", 'danger')
        return redirect(url_for('index', sekcja=sekcja))

@api_bp.route('/zapisz-raport-koncowy-global', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_raport_koncowy_global():
    """Zapisz raport końcowy i zamknij zmianę - WSZYSTKIE SEKCJE"""
    dzisiaj = date.today()
    notatki = request.form.get('notatki', '')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz dane dla ALL sekcji z paletami
        wszystkie_plany = {}
        sekcje = ['Zasyp', 'Workowanie', 'Magazyn']
        
        for sekcja in sekcje:
            cursor.execute("""
                SELECT id, produkt, tonaz, tonaz_rzeczywisty, status
                FROM plan_produkcji
                WHERE data_planu = %s AND sekcja = %s
            """, (dzisiaj, sekcja))
            
            plany_data = []
            for row in cursor.fetchall():
                plan_id = row[0]
                
                # Pobierz palety dla tego planu
                cursor.execute("""
                    SELECT waga, data_dodania, status
                    FROM palety_workowanie
                    WHERE plan_id = %s
                    ORDER BY data_dodania DESC
                """, (plan_id,))
                
                palety = []
                for p_row in cursor.fetchall():
                    palety.append({
                        'waga': p_row[0],
                        'data_dodania': p_row[1].isoformat() if p_row[1] else 'N/A',
                        'status': p_row[2]
                    })
                
                plany_data.append({
                    'id': plan_id,
                    'produkt': row[1],
                    'tonaz': row[2],
                    'tonaz_wykonania': row[3] or 0,
                    'status': row[4],
                    'palety': palety
                })
            wszystkie_plany[sekcja] = plany_data
        
        # Pobierz obsadę per sekcja
        wszystkie_obsady = {}
        for sekcja in sekcje:
            cursor.execute("""
                SELECT DISTINCT pw.id, pw.imie_nazwisko, pw.rola
                FROM obsada_zmiany oz
                JOIN pracownicy pw ON oz.pracownik_id = pw.id
                WHERE oz.data_wpisu = %s AND oz.sekcja = %s
                ORDER BY pw.imie_nazwisko
            """, (dzisiaj, sekcja))
            
            obsada = []
            for row in cursor.fetchall():
                obsada.append({
                    'id': row[0],
                    'imie_nazwisko': row[1],
                    'rola': row[2]
                })
            wszystkie_obsady[sekcja] = obsada
        
        # Pobierz wpisy o awariach/usterkach
        cursor.execute("""
            SELECT DISTINCT sekcja, typ, opis, data_wpisu, pracownik_id
            FROM dziennik_wpisy
            WHERE data_wpisu = %s AND typ IN ('awaria', 'usterka', 'nieobecność', 'przerwa')
            ORDER BY sekcja, data_wpisu DESC
        """, (dzisiaj,))
        
        awarie = []
        for row in cursor.fetchall():
            sekcja, typ, opis, data_wpisu, pracownik_id = row
            pracownik_name = 'N/A'
            if pracownik_id:
                cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                p_row = cursor.fetchone()
                pracownik_name = p_row[0] if p_row else 'N/A'
            
            awarie.append({
                'sekcja': sekcja,
                'typ': typ,
                'opis': opis,
                'data_wpisu': data_wpisu.strftime('%H:%M:%S') if data_wpisu else 'N/A',
                'pracownik': pracownik_name
            })
        
        lider_id = session.get('pracownik_id')
        
        # Przygotuj dane do zapisania
        zmiana_summary = {
            'data': dzisiaj.isoformat(),
            'sekcje': sekcje,
            'lider_id': lider_id,
            'wszystkie_plany': wszystkie_plany,
            'wszystkie_obsady': wszystkie_obsady,
            'awarie': awarie,
            'notatki': notatki
        }
        
        # Zapisz raport do bazy (bez konkretnej sekcji)
        import json
        cursor.execute("""
            INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json)
            VALUES (%s, %s, %s, %s, %s)
        """, (dzisiaj, 'Wszystkie sekcje', lider_id, notatki, json.dumps(zmiana_summary)))
        
        # Oznacz WSZYSTKIE plany jako zamknięte
        for sekcja in sekcje:
            cursor.execute("""
                UPDATE plan_produkcji
                SET status = 'zamknieta'
                WHERE data_planu = %s AND sekcja = %s AND status != 'zamknieta'
            """, (dzisiaj, sekcja))
        
        conn.commit()
        conn.close()
        
        flash(f"✅ Zmiana została zamknięta dla wszystkich sekcji!", 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        current_app.logger.error(f"Błąd przy zamykaniu zmiany: {e}")
        flash(f"❌ Błąd: {str(e)}", 'danger')
        return redirect(url_for('index'))

@api_bp.route('/pobierz-raport', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def pobierz_raport():
    """Pobierz wygenerowany raport (PDF, Excel, TXT)"""
    try:
        raport_format = request.form.get('format', 'email')
        
        # Pobierz ostatni raport dla dzisiaj z bazy
        dzisiaj = date.today()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT summary_json, sekcja, data_raportu, lider_id
            FROM raporty_koncowe 
            WHERE data_raportu = %s 
            ORDER BY id DESC 
            LIMIT 1
        """, (dzisiaj,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            flash("❌ Raport nie znaleziony!", 'danger')
            return redirect(url_for('index'))
        
        raw_data = json.loads(result[0])
        sekcja = result[1]
        data_raportu = result[2]
        lider_id = result[3]
        
        # Pobierz dane lidera
        cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (lider_id,))
        lider_row = cursor.fetchone()
        lider_name = lider_row[0] if lider_row else 'N/A'
        conn.close()
        
        # Transform danych do formatu oczekiwanego przez RaportService
        if 'wszystkie_plany' in raw_data:
            # Global report - wszystkie sekcje
            plany_flatten = []
            for sekcja_name, sekcja_plany in raw_data.get('wszystkie_plany', {}).items():
                for plan in sekcja_plany:
                    plan_copy = plan.copy()
                    plan_copy['sekcja'] = sekcja_name
                    # Dodaj domyślne wartości dla starych raportów bez status/palety
                    if 'status' not in plan_copy:
                        plan_copy['status'] = 'zamknieta'
                    if 'palety' not in plan_copy:
                        plan_copy['palety'] = []
                    plany_flatten.append(plan_copy)
            
            zmiana_data = {
                'data': raw_data.get('data', dzisiaj.isoformat()),
                'sekcja': 'Wszystkie sekcje',
                'lider_name': lider_name,
                'pracownicy': raw_data.get('pracownicy', []),
                'plany': plany_flatten,
                'notatki': raw_data.get('notatki', '')
            }
        else:
            # Single sekcja report
            plany = raw_data.get('plany', [])
            for plan in plany:
                # Dodaj domyślne wartości dla starych raportów
                if 'status' not in plan:
                    plan['status'] = 'zamknieta'
                if 'palety' not in plan:
                    plan['palety'] = []
            
            zmiana_data = {
                'data': raw_data.get('data', dzisiaj.isoformat()),
                'sekcja': raw_data.get('sekcja', sekcja),
                'lider_name': lider_name,
                'pracownicy': raw_data.get('pracownicy', []),
                'plany': plany,
                'notatki': raw_data.get('notatki', '')
            }
        
        if raport_format == 'email':
            content = RaportService.generate_email_text(zmiana_data)
            return content, 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': f'attachment; filename="Raport_{data_raportu}.txt"'
            }
        
        elif raport_format == 'excel':
            try:
                content = RaportService.generate_excel(zmiana_data)
                return send_file(
                    BytesIO(content),
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=f'Raport_{data_raportu}.xlsx'
                )
            except Exception as e:
                current_app.logger.error(f"Błąd generowania Excel: {e}")
                flash("❌ Excel nie zainstalowany. Spróbuj formatu txt.", 'warning')
                return redirect(url_for('index'))
        
        elif raport_format == 'pdf':
            try:
                content = RaportService.generate_pdf(zmiana_data)
                return send_file(
                    BytesIO(content),
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'Raport_{data_raportu}.pdf'
                )
            except Exception as e:
                current_app.logger.error(f"Błąd generowania PDF: {e}")
                flash("❌ ReportLab nie zainstalowany. Spróbuj formatu txt.", 'warning')
                return redirect(url_for('index'))
        
        else:
            flash("❌ Nieznany format raportu!", 'danger')
            return redirect(url_for('index'))
        
    except Exception as e:
        current_app.logger.error(f"Błąd przy pobieraniu raportu: {e}")
        flash(f"❌ Błąd: {str(e)}", 'danger')
        return redirect(url_for('index'))
