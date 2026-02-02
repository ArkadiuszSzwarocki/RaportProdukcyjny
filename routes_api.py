from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from utils.validation import require_field
import logging
import json
from datetime import date, datetime, timedelta, time
from io import BytesIO
from db import get_db_connection, rollover_unfinished, log_plan_history
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
    cursor.execute("SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status, COALESCE(tonaz_rzeczywisty, 0) FROM plan_produkcji WHERE id=%s", (id,))
    z = cursor.fetchone()
    
    if z:
        produkt, tonaz, sekcja, data_planu, typ, status_obecny, tonaz_rzeczywisty_zasyp = z
        if status_obecny != 'w toku':
            cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
            cursor.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW(), real_stop=NULL WHERE id=%s", (id,))
        
        if sekcja == 'Zasyp' and status_obecny == 'zaplanowane':
            # When starting Zasyp order, create Workowanie plan with tonaz_rzeczywisty = 0
            # Actual weight will be added later when batches (szarże) are added
            cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND typ_produkcji=%s", (data_planu, produkt, typ))
            istniejace = cursor.fetchone()
            if not istniejace:
                cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
                res = cursor.fetchone()
                mk = res[0] if res and res[0] else 0
                nk = mk + 1
                # INSERT with tonaz_rzeczywisty = 0 (no actual weight yet - will be added by szarżę)
                cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, 'Workowanie', %s, %s, 'zaplanowane', %s, %s, %s)", (data_planu, produkt, tonaz, nk, typ, 0))
            else:
                # Update existing Workowanie plan: keep tonaz fixed, reset tonaz_rzeczywisty to 0
                cursor.execute("UPDATE plan_produkcji SET tonaz=%s, tonaz_rzeczywisty=0 WHERE id=%s", (tonaz, istniejace[0]))
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
    # Render a confirmation fragment that posts to existing /koniec_zlecenie/<id>
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Zasyp'))
    produkt = None
    tonaz = None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT produkt, tonaz FROM plan_produkcji WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            produkt, tonaz = row[0], row[1]
    except Exception:
        try: current_app.logger.exception('Failed to fetch plan %s for koniec_zlecenie_page', id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass

    return render_template('koniec_zlecenie.html', id=id, sekcja=sekcja, produkt=produkt, tonaz=tonaz)


# Temporary test endpoint: return the most recent file from raporty/ as attachment
@api_bp.route('/test-pobierz-raport', methods=['GET'])
@login_required
def api_test_pobierz_raport():
    import os, glob
    rap_dir = os.path.join(current_app.root_path, 'raporty')
    if not os.path.isdir(rap_dir):
        return jsonify({'error': 'raporty directory not found'}), 404
    files = glob.glob(os.path.join(rap_dir, '*'))
    if not files:
        return jsonify({'error': 'no reports available'}), 404
    latest = max(files, key=os.path.getmtime)
    try:
        return send_file(latest, as_attachment=True, download_name=os.path.basename(latest))
    except Exception:
        try: current_app.logger.exception('Failed to send report %s', latest)
        except Exception: pass
        return jsonify({'error': 'failed to send file'}), 500


@api_bp.route('/szarza_page/<int:plan_id>', methods=['GET'])
@login_required
def szarza_page(plan_id):
    # Render a simple form to add a szarża (delegates to dodaj_palete POST)
    # Fetch plan details (produkt, typ) from DB - these should be pre-filled
    current_app.logger.info(f'[SZARZA_PAGE] Called with plan_id={plan_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT produkt, typ_produkcji FROM plan_produkcji WHERE id=%s AND sekcja='Zasyp'",
            (plan_id,)
        )
        plan = cursor.fetchone()
        if not plan:
            conn.close()
            current_app.logger.warning(f'[SZARZA_PAGE] Plan {plan_id} not found')
            flash('Plan nie znaleziony', 'error')
            return redirect('/')
        
        produkt, typ_produkcji = plan[0], plan[1]
        conn.close()
        current_app.logger.info(f'[SZARZA_PAGE] Rendering form for plan_id={plan_id}, produkt={produkt}, typ={typ_produkcji}')
        return render_template('dodaj_palete_popup.html', 
                             plan_id=plan_id, 
                             sekcja='Zasyp',
                             produkt=produkt,
                             typ=typ_produkcji)
    except Exception as e:
        conn.close()
        current_app.logger.error(f'[SZARZA_PAGE] Error in szarza_page: {e}')
        flash('Błąd pobierania danych planu', 'error')
        return redirect('/')


@api_bp.route('/wyjasnij_page/<int:id>', methods=['GET'])
@login_required
def wyjasnij_page(id):
    # Render form to submit wyjasnienie via zapisz_wyjasnienie
    return render_template('wyjasnij.html', id=id)


@api_bp.route('/manual_rollover', methods=['POST'])
@roles_required('lider', 'admin')
def manual_rollover():
    from_date = request.form.get('from_date') or request.args.get('from_date')
    to_date = request.form.get('to_date') or request.args.get('to_date')
    if not from_date or not to_date:
        flash('Brakuje daty źródłowej lub docelowej', 'error')
        return redirect(bezpieczny_powrot())

    try:
        added = rollover_unfinished(from_date, to_date)
        flash(f'Przeniesiono {added} zleceń z {from_date} na {to_date}', 'success')
    except Exception as e:
        current_app.logger.exception('manual_rollover failed: %s', e)
        flash('Błąd podczas przenoszenia zleceń', 'error')

    return redirect(bezpieczny_powrot())


@api_bp.route('/obsada_page', methods=['GET'])
@login_required
def obsada_page():
    """Render small slide-over for managing `obsada` (workers on shift) for a sekcja."""
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Workowanie'))
    # allow optional date parameter (YYYY-MM-DD) to view/modify obsada for other dates
    date_str = request.args.get('date') or request.form.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # all obsada entries for given date (grouped by sekcja)
        cursor.execute("SELECT oz.sekcja, oz.id, p.imie_nazwisko FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s ORDER BY oz.sekcja, p.imie_nazwisko", (qdate,))
        rows = cursor.fetchall()
        obsady_map = {}
        for r in rows:
            sekc, oz_id, name = r[0], r[1], r[2]
            obsady_map.setdefault(sekc, []).append((oz_id, name))
        # available employees: exclude those already assigned for that date (any sekcja)
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu=%s) ORDER BY imie_nazwisko", (qdate,))
        wszyscy = cursor.fetchall()
        # pełna lista pracowników (dla wyboru liderów)
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        all_pracownicy = cursor.fetchall()
        # pobierz liderów dla tej daty (jeśli istnieją)
        cursor.execute("SELECT lider_psd_id, lider_agro_id FROM obsada_liderzy WHERE data_wpisu=%s", (qdate,))
        lider_row = cursor.fetchone()
        lider_psd_id = lider_row[0] if lider_row else None
        lider_agro_id = lider_row[1] if lider_row else None
    finally:
        try: conn.close()
        except Exception: pass

    # If requested via AJAX, return only the fragment (no full layout)
    try:
        is_ajax = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'
    except Exception:
        is_ajax = False

    if is_ajax:
        return render_template('obsada_fragment.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)

    return render_template('obsada.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)

# ================= PALETY =================

@api_bp.route('/dodaj_palete/<int:plan_id>', methods=['POST'])
@login_required
def dodaj_palete(plan_id):
    """
    REFACTORED: Add paleta (package) to Workowanie buffer only.
    No automatic plan creation - buffer should already exist created by dodaj_plan().
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_app.logger.info('API dodaj_palete called plan_id=%s', plan_id)
    except Exception:
        pass
    
    try:
        waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
    except Exception:
        waga_input = 0
    
    # Get plan details
    cursor.execute("SELECT sekcja, data_planu, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
    plan_row = cursor.fetchone()
    
    if not plan_row:
        conn.close()
        return ("Błąd: Plan nie znaleziony", 404)
    
    plan_sekcja, plan_data, plan_produkt = plan_row
    
    # REFACTORED: Only allow adding paleta to Workowanie (buffer)
    # Zasyp should use dodaj_plan() to create szarże
    if plan_sekcja != 'Workowanie':
        conn.close()
        try:
            current_app.logger.warning(f'REJECTED: Cannot add paleta to sekcja={plan_sekcja}. Use dodaj_plan() for Zasyp szarże.')
        except Exception:
            pass
        return ("Błąd: Paletki można dodawać tylko do Workowania (bufora). Użyj 'Dodaj szarżę' dla Zasypu.", 400)
    
    # Validate weight
    if waga_input <= 0:
        conn.close()
        return ("Błąd: Waga musi być większa od 0", 400)
    
    # Add paleta to buffer (Workowanie plan)
    from datetime import datetime as _dt
    now_ts = _dt.now()
    
    try:
        cursor.execute(
            "INSERT INTO palety_workowanie (plan_id, waga, tara, waga_brutto, data_dodania, status) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia')",
            (plan_id, waga_input, now_ts)
        )
        paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
        
        # Update buffer tonaz_rzeczywisty: subtract this paleta from buffer (buffer stores incoming from szarze)
        cursor.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) - %s WHERE id = %s",
            (waga_input, plan_id)
        )
        
        conn.commit()
        try:
            current_app.logger.info(f'✓ Added paleta to Workowanie (buffer): plan_id={plan_id}, waga={waga_input}kg')
        except Exception:
            pass
        
    except Exception as e:
        try:
            current_app.logger.exception(f'Failed to add paleta: {str(e)}')
        except Exception:
            pass
        conn.rollback()
        conn.close()
        return ("Błąd: Nie udało się dodać paletki", 500)
    
    conn.close()
    
    # Return JSON for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Paletka dodana', 'paleta_id': paleta_id}), 200
    
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
    # Render popup variant for adding paleta (Zasyp-friendly popup)
    return render_template('dodaj_palete_popup.html', plan_id=plan_id, produkt=produkt, sekcja=sekcja, typ=typ)


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
    # Render popup variant for editing paleta
    return render_template('edytuj_palete_popup.html', paleta_id=paleta_id, waga=waga, sekcja=sekcja)



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
                # Recompute total for the plan (exclude confirmed palety - only count unconfirmed)
                try:
                    cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
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


@api_bp.route('/bufor', methods=['GET'])
def api_bufor():
    """Public API (no auth) returning bufor entries as JSON for testing.
    Query params: data=YYYY-MM-DD (optional, defaults to today)
    """
    from datetime import date as _date
    out = []
    qdate = request.args.get('data') or str(_date.today())
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, data_planu, produkt, tonaz_rzeczywisty, nazwa_zlecenia, typ_produkcji
            FROM plan_produkcji
            WHERE sekcja = 'Zasyp'
              AND data_planu >= DATE_SUB(%s, INTERVAL 7 DAY)
              AND data_planu <= %s
        """, (qdate, qdate))
        rows = cur.fetchall()
        for hz in rows:
            h_id, h_data, h_produkt, h_wykonanie_zasyp, h_nazwa, h_typ = hz
            typ_param = h_typ if h_typ is not None else ''
            cur.execute(
                "SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s OR plan_id IN (SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s)",
                (h_id, h_data, h_produkt, typ_param)
            )
            res_pal = cur.fetchone()
            h_wykonanie_workowanie = res_pal[0] if res_pal and res_pal[0] else 0
            pozostalo_w_silosie = (h_wykonanie_zasyp or 0) - (h_wykonanie_workowanie or 0)
            needs_reconciliation = round((h_wykonanie_workowanie or 0) - (h_wykonanie_zasyp or 0), 1) != 0
            show_in_bufor = (pozostalo_w_silosie > 0) or (h_wykonanie_workowanie and h_wykonanie_workowanie > 0)
            if show_in_bufor:
                out.append({
                    'id': h_id,
                    'data': str(h_data),
                    'produkt': h_produkt,
                    'nazwa': h_nazwa,
                    'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                    'typ_produkcji': h_typ,
                    'zasyp_total': h_wykonanie_zasyp,
                    'spakowano_total': h_wykonanie_workowanie,
                    'needs_reconciliation': needs_reconciliation,
                    'raw_pozostalo': round(pozostalo_w_silosie, 1)
                })
    except Exception:
        try: conn.close()
        except Exception: pass
        return jsonify({'bufor': [], 'error': True}), 500
    finally:
        try: conn.close()
        except Exception: pass

    return jsonify({'bufor': out})

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
        # Recompute buffer: exclude confirmed palety (only count unconfirmed 'do_przyjecia')
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
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
        # Recompute buffer: exclude confirmed palety (only count unconfirmed 'do_przyjecia')
        cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
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
        # Zaktualizuj sumę w plan_produkcji (exclude confirmed palety - only count unconfirmed 'do_przyjecia')
        cursor.execute("SELECT plan_id FROM palety_workowanie WHERE id=%s", (paleta_id,))
        res = cursor.fetchone()
        if res:
            plan_id = res[0]
            cursor.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s", (plan_id, plan_id))
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
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, status, sekcja, nk, typ, 0))
    conn.commit()
    conn.close()
    return redirect(url_for('planista.panel_planisty', data=data_planu))


@api_bp.route('/dodaj_plan', methods=['POST'])
@roles_required('planista', 'admin', 'lider', 'produkcja', 'pracownik')
def dodaj_plan():
    # Backwards-compatible simple add used by small section widgets
    data_planu = request.form.get('data_planu') or request.form.get('data') or str(date.today())
    from utils.validation import require_field
    
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
        # - Szarża (Zasyp): Zwiększa tonaz_rzeczywisty PODANEGO planu Zasyp (plan_id) + zwiększa bufor Workowanie
        # - Paleta (Workowanie): Zmniejsza bufor Workowanie
        
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
                
                # Insert szarża do tabeli szarze
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
                
                # Also increase buffer (Workowanie) tonaz_rzeczywisty
                cursor.execute(
                    "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s ORDER BY id LIMIT 1",
                    (data_planu, produkt, typ)
                )
                buffer_plan = cursor.fetchone()
                if buffer_plan:
                    buffer_id = buffer_plan[0]
                    cursor.execute(
                        "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id=%s",
                        (tonaz, buffer_id)
                    )
                    try:
                        current_app.logger.warning(f'[DODAJ_PLAN] Increased buffer (Workowanie) plan {buffer_id}')
                    except Exception:
                        pass
                
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
    
    # REFACTORED: If adding a szarża (batch) to Zasyp, automatically create corresponding buffer (plan) in Workowanie
    if sekcja == 'Zasyp' and tonaz > 0 and zasyp_plan_id:
        try:
            # Check if Workowanie plan already exists for this product/type
            cursor.execute("SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s LIMIT 1", (data_planu, produkt, typ))
            existing_work = cursor.fetchone()
            if not existing_work:
                # Create buffer (Workowanie plan) with tonaz = szarża weight
                nk_work = nk + 1
                cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, 'zaplanowane', 'Workowanie', %s, %s, %s)", (data_planu, produkt, tonaz, nk_work, typ, 0))
                try:
                    current_app.logger.info(f'Auto-created buffer (Workowanie plan) for szarża (Zasyp plan_id={zasyp_plan_id}) with tonaz={tonaz}')
                except Exception:
                    pass
        except Exception as e:
            try:
                current_app.logger.warning(f'Failed to auto-create buffer: {str(e)}')
            except Exception:
                pass
    
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
            cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', sekcja, nk, typ, nr, 0))
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


@api_bp.route('/edytuj_plan/<int:id>', methods=['POST'])
@roles_required('planista', 'admin')
def edytuj_plan(id):
    """Zapisuje edycję pól planu: produkt, tonaz, sekcja, data_planu."""
    from utils.validation import require_field
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
        # Sprawdź czy istnieje
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
            updates.append('produkt=%s'); params.append(produkt)
        if tonaz_val is not None:
            updates.append('tonaz=%s'); params.append(tonaz_val)
        if sekcja:
            updates.append('sekcja=%s'); params.append(sekcja)
        if data_planu:
            # jeśli zmieniamy datę, ustawimy nową kolejność na koniec dnia
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
            res = cursor.fetchone(); nk = (res[0] if res and res[0] else 0) + 1
            updates.append('data_planu=%s'); params.append(data_planu)
            updates.append('kolejnosc=%s'); params.append(nk)

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


@api_bp.route('/edytuj_plan_ajax', methods=['POST'])
@roles_required('planista', 'admin')
def edytuj_plan_ajax():
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
            updates.append('produkt=%s'); params.append(produkt); changes['produkt'] = {'before': before[1], 'after': produkt}
        if tonaz_val is not None and tonaz_val != (before[2] or 0):
            updates.append('tonaz=%s'); params.append(tonaz_val); changes['tonaz'] = {'before': before[2], 'after': tonaz_val}
        if sekcja and sekcja != before[3]:
            updates.append('sekcja=%s'); params.append(sekcja); changes['sekcja'] = {'before': before[3], 'after': sekcja}
        if data_planu and data_planu != str(before[4]):
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
            res = cursor.fetchone(); nk = (res[0] if res and res[0] else 0) + 1
            updates.append('data_planu=%s'); params.append(data_planu); updates.append('kolejnosc=%s'); params.append(nk)
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


@api_bp.route('/przenies_zlecenie_ajax', methods=['POST'])
@roles_required('planista', 'admin')
def przenies_zlecenie_ajax():
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

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status, data_planu FROM plan_produkcji WHERE id=%s", (pid,))
        row = cursor.fetchone()
        if not row:
            conn.close(); return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404
        if row[0] in ['w toku', 'zakonczone']:
            conn.close(); return jsonify({'success': False, 'message': 'Nie można przenieść zlecenia w toku lub zakończonego'}), 403
        old_date = row[1]
        cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (to_date,))
        res = cursor.fetchone(); nk = (res[0] if res and res[0] else 0) + 1
        cursor.execute("UPDATE plan_produkcji SET data_planu=%s, kolejnosc=%s WHERE id=%s", (to_date, nk, pid))
        conn.commit()
        try:
            user_login = session.get('login') or session.get('imie_nazwisko')
        except Exception:
            user_login = None
        try:
            log_plan_history(pid, 'move', json.dumps({'from': str(old_date), 'to': to_date}, ensure_ascii=False), user_login)
        except Exception:
            pass
        conn.close()
        return jsonify({'success': True, 'message': 'Przeniesiono'})
    except Exception:
        current_app.logger.exception('przenies_zlecenie_ajax failed')
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500


@api_bp.route('/przesun_zlecenie_ajax', methods=['POST'])
@roles_required('planista', 'admin')
def przesun_zlecenie_ajax():
    try:
        data = request.get_json(force=True)
    except Exception:
        data = request.form.to_dict()
    id = data.get('id')
    kierunek = data.get('kierunek')
    data_date = data.get('data') or request.args.get('data') or str(date.today())
    if not id or not kierunek:
        return jsonify({'success': False, 'message': 'Brak parametrów'}), 400
    try:
        pid = int(id)
    except Exception:
        return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, kolejnosc, status FROM plan_produkcji WHERE id=%s", (pid,))
        obecne = cursor.fetchone()
        if not obecne:
            conn.close(); return jsonify({'success': False, 'message': 'Nie znaleziono zlecenia'}), 404
        if obecne[2] in ['w toku', 'zakonczone']:
            conn.close(); return jsonify({'success': False, 'message': 'Nie można przenieść zlecenia w toku lub zakończonego'}), 403

        oid, okol, _ = obecne
        q = "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc < %s ORDER BY kolejnosc DESC LIMIT 1" if kierunek == 'gora' else "SELECT id, kolejnosc FROM plan_produkcji WHERE data_planu=%s AND kolejnosc > %s ORDER BY kolejnosc ASC LIMIT 1"
        cursor.execute(q, (data_date, okol))
        sasiad = cursor.fetchone()
        if sasiad:
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (sasiad[1], oid))
            cursor.execute("UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s", (okol, sasiad[0]))
            conn.commit()
            # log history
            try:
                user_login = session.get('login') or session.get('imie_nazwisko')
            except Exception:
                user_login = None
            try:
                log_plan_history(pid, 'reorder', json.dumps({'direction': kierunek, 'swapped_with': sasiad[0]}, ensure_ascii=False), user_login)
            except Exception:
                pass
            conn.close()
            return jsonify({'success': True, 'message': 'Przeniesiono'})

        conn.close()
        return jsonify({'success': False, 'message': 'Brak sąsiada do zamiany'}), 400
    except Exception:
        current_app.logger.exception('przesun_zlecenie_ajax failed')
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500


@api_bp.route('/usun_plan_ajax/<int:id>', methods=['POST'])
@roles_required('planista', 'admin')
def api_usun_plan(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status, produkt, data_planu, tonaz FROM plan_produkcji WHERE id=%s", (id,))
        res = cursor.fetchone()
        if not res:
            conn.close(); return jsonify({'success': False, 'message': 'Zlecenie nie istnieje.'}), 404
        if res[0] in ['w toku', 'zakonczone']:
            conn.close(); return jsonify({'success': False, 'message': 'Nie można usunąć zleczenia w toku lub już zakończonego.'}), 403

        # record details for history
        details = {'produkt': res[1], 'data_planu': str(res[2]), 'tonaz': res[3]}
        # delete related palety and plan
        cursor.execute("DELETE FROM palety_workowanie WHERE plan_id=%s", (id,))
        cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (id,))
        conn.commit()
        try:
            user_login = session.get('login') or session.get('imie_nazwisko')
        except Exception:
            user_login = None
        try:
            log_plan_history(id, 'delete', json.dumps(details, ensure_ascii=False), user_login)
        except Exception:
            pass
        conn.close()
        return jsonify({'success': True, 'message': 'Zlecenie zostało usunięte.'})
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        current_app.logger.exception('Failed to delete plan %s', id)
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Wystąpił błąd przy usuwaniu zlecenia.'}), 500


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
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', 'Zasyp', nk, typ, 0))
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


@api_bp.route('/panel/wnioski', methods=['GET'])
@roles_required('lider', 'admin')
def panel_wnioski():
    """Zwraca fragment HTML z listą oczekujących wniosków (slide-over)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.powod, w.zlozono FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id WHERE w.status = 'pending' ORDER BY w.zlozono DESC LIMIT 200")
        raw = cursor.fetchall()
        wnioski = []
        for r in raw:
            wnioski.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3], 'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'powod': r[7], 'zlozono': r[8]})
        try:
            conn.close()
        except Exception:
            pass
        return render_template('panels/wnioski_panel.html', wnioski=wnioski)
    except Exception:
        current_app.logger.exception('Failed to build wnioski panel')
        return render_template('panels/wnioski_panel.html', wnioski=[])


@api_bp.route('/panel/planowane', methods=['GET'])
@login_required
def panel_planowane():
    """Zwraca fragment HTML z planowanymi urlopami (następne 60 dni)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        end_date = date.today() + timedelta(days=60)
        cursor.execute("SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.status FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id WHERE w.data_od <= %s AND w.data_do >= %s ORDER BY w.data_od ASC LIMIT 500", (end_date, date.today()))
        raw = cursor.fetchall()
        planned = []
        for r in raw:
            planned.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3], 'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'status': r[7]})
        try:
            conn.close()
        except Exception:
            pass
        return render_template('panels/planowane_panel.html', planned_leaves=planned)
    except Exception:
        current_app.logger.exception('Failed to build planned leaves panel')
        return render_template('panels/planowane_panel.html', planned_leaves=[])


@api_bp.route('/panel/obecnosci', methods=['GET'])
@login_required
def panel_obecnosci():
    """Zwraca fragment HTML z ostatnimi nieobecnościami (ostatnie 30 dni)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        since = date.today() - timedelta(days=30)
        cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu BETWEEN %s AND %s ORDER BY o.data_wpisu DESC LIMIT 500", (since, date.today()))
        raw = cursor.fetchall()
        recent = []
        for r in raw:
            recent.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data': r[3], 'godziny': r[4], 'komentarz': r[5]})
        try:
            conn.close()
        except Exception:
            pass
        return render_template('panels/obecnosci_panel.html', recent_absences=recent)
    except Exception:
        current_app.logger.exception('Failed to build absences panel')
        return render_template('panels/obecnosci_panel.html', recent_absences=[])
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
    # allow optional date parameter to assign obsada for a specific day
    date_str = request.form.get('date') or request.args.get('date')
    try:
        add_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        add_date = date.today()
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
        cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (add_date, sekcja, pracownik_id))
        # Attempt to retrieve the inserted row id for AJAX clients
        try:
            cursor.execute("SELECT id FROM obsada_zmiany WHERE data_wpisu=%s AND sekcja=%s AND pracownik_id=%s ORDER BY id DESC LIMIT 1", (add_date, sekcja, pracownik_id))
            inserted_row = cursor.fetchone()
            inserted_id = inserted_row[0] if inserted_row else None
        except Exception:
            inserted_id = None
        # Automatyczne zapisanie obecności przy dodaniu do obsady (jeśli brak już wpisu)
        try:
            default_hours = 8
            cursor.execute("SELECT COUNT(1) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, add_date))
            exists = int(cursor.fetchone()[0] or 0)
            if not exists:
                cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (add_date, pracownik_id, 'Obecność', default_hours, 'Automatyczne z obsady'))
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


@api_bp.route('/zapisz_liderow_obsady', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_liderow_obsady():
    date_str = request.form.get('date') or request.args.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()
    lider_psd = request.form.get('lider_psd') or None
    lider_agro = request.form.get('lider_agro') or None

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # upsert leaders for that date
        cur.execute("INSERT INTO obsada_liderzy (data_wpisu, lider_psd_id, lider_agro_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE lider_psd_id=VALUES(lider_psd_id), lider_agro_id=VALUES(lider_agro_id)", (qdate, lider_psd, lider_agro))
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(bezpieczny_powrot())

@api_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # pobierz informacje o usuwanym wierszu i usuń wszystkie powielone wpisy
        cursor.execute("SELECT pracownik_id, data_wpisu, sekcja FROM obsada_zmiany WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            pracownik_id, data_wpisu, sekcja = row[0], row[1], row[2]
            cursor.execute("DELETE FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s AND sekcja=%s", (pracownik_id, data_wpisu, sekcja))
            # Usuń automatyczny wpis w tabeli obecnosc utworzony przy dodaniu do obsady
            try:
                cursor.execute("DELETE FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s AND komentarz=%s", (pracownik_id, data_wpisu, 'Automatyczne z obsady'))
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
        else:
            cursor.execute("DELETE FROM obsada_zmiany WHERE id=%s", (id,))
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass

    # dla AJAX zwracamy JSON, dla zwykłego formularza redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
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
        # Pobierz imię i nazwisko lidera — preferuj wybór z formularza jeśli podano
        lider_name = "Nieznany"
        pracownik_id = session.get('pracownik_id')
        lider_login = session.get('login', 'nieznany')

        # If form provided a leader, prefer that
        form_lider_id = request.form.get('lider_id') or request.values.get('lider_id')
        form_lider_prowadzacy_id = request.form.get('lider_prowadzacy_id') or request.values.get('lider_prowadzacy_id')

        print(f"[ROUTE] Looking for lider: session_pracownik_id={pracownik_id}, form_lider_id={form_lider_id}, login={lider_login}")

        try:
            conn_user = get_db_connection()
            cursor_user = conn_user.cursor()
            chosen_lider_id = form_lider_id if form_lider_id else pracownik_id
            if chosen_lider_id:
                cursor_user.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (chosen_lider_id,))
                row = cursor_user.fetchone()
                if row and row[0]:
                    lider_name = row[0]
                    print(f"[ROUTE] ✓ Found lider name: {lider_name} (id={chosen_lider_id})")
            else:
                lider_name = lider_login

            # If a 'lider_prowadzacy' was provided, fetch name and append to uwagi
            if form_lider_prowadzacy_id:
                cursor_user.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (form_lider_prowadzacy_id,))
                row2 = cursor_user.fetchone()
                if row2 and row2[0]:
                    prowadzacy_name = row2[0]
                    uwagi = (uwagi or '') + f"\nLider prowadzący: {prowadzacy_name}\n"
                    print(f"[ROUTE] ✓ Lider prowadzący: {prowadzacy_name} (id={form_lider_prowadzacy_id})")

            cursor_user.close()
            conn_user.close()
        except Exception as e:
            print(f"[ROUTE] ✗ Error fetching leader names: {e}")
        
        # Generuj raporty
        date_str = dzisiaj.strftime('%Y-%m-%d')
        print(f"[ROUTE] Calling generator with date={date_str}, lider={lider_name}, uwagi_len={len(uwagi)}")
        xls_path, txt_path, pdf_path = generuj_paczke_raportow(date_str, uwagi, lider_name)
        
        # Loguj sukces
        print(f"[ROUTE] ✓ Reports generated successfully!")
        print(f"[ROUTE] Excel: {xls_path}")
        print(f"[ROUTE] TXT: {txt_path}")
        print(f"[ROUTE] PDF: {pdf_path}")
        
        # Przenieś wygenerowane pliki z raporty_temp do raporty (jeśli są tam)
        import os
        import zipfile
        import shutil
        from io import BytesIO
        
        raporty_dir = 'raporty'
        if not os.path.exists(raporty_dir):
            os.makedirs(raporty_dir)
        
        # Przeniesienie Excel
        final_xls = xls_path
        if xls_path and os.path.exists(xls_path) and 'raporty_temp' in xls_path:
            try:
                final_xls = os.path.join(raporty_dir, os.path.basename(xls_path))
                shutil.move(xls_path, final_xls)
                print(f"[ROUTE] Moved Excel to {final_xls}")
            except Exception as e:
                print(f"[ROUTE] Could not move Excel: {e}")
                final_xls = xls_path
        
        # Przeniesienie TXT
        final_txt = txt_path
        if txt_path and os.path.exists(txt_path) and 'raporty_temp' in txt_path:
            try:
                final_txt = os.path.join(raporty_dir, os.path.basename(txt_path))
                shutil.move(txt_path, final_txt)
                print(f"[ROUTE] Moved TXT to {final_txt}")
            except Exception as e:
                print(f"[ROUTE] Could not move TXT: {e}")
                final_txt = txt_path
        
        # Stwórz ZIP z wszystkimi plikami
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Dodaj Excel
            if final_xls and os.path.exists(final_xls):
                zip_file.write(final_xls, arcname=os.path.basename(final_xls))
                print(f"[ROUTE] ✓ Added to ZIP: {os.path.basename(final_xls)}")
            else:
                print(f"[ROUTE] ✗ Excel file not found: {final_xls}")
            
            # Dodaj TXT
            if final_txt and os.path.exists(final_txt):
                zip_file.write(final_txt, arcname=os.path.basename(final_txt))
                print(f"[ROUTE] ✓ Added to ZIP: {os.path.basename(final_txt)}")
            else:
                print(f"[ROUTE] ✗ TXT file not found: {final_txt}")
            
            # Dodaj PDF
            if pdf_path and os.path.exists(pdf_path):
                zip_file.write(pdf_path, arcname=os.path.basename(pdf_path))
                print(f"[ROUTE] ✓ Added to ZIP: {os.path.basename(pdf_path)}")
            else:
                print(f"[ROUTE] ✗ PDF file not found: {pdf_path}")
        
        zip_buffer.seek(0)
        zip_filename = f"Raporty_{date_str}.zip"
        print(f"[ROUTE] ✓ ZIP created: {zip_filename}")
        
        # ================= ZAWIESZENIE ZLECEŃ PO ZAMKNIĘCIU ZMIANY =================
        try:
            conn_plans = get_db_connection()
            cursor_plans = conn_plans.cursor()
            
            # Zawieszaj wszystkie zlecenia ze status = 'w toku' dla dzisiejszego dnia
            suspend_query = """
                UPDATE plan_produkcji 
                SET status = 'wstrzymane' 
                WHERE DATE(data_planu) = %s 
                AND status = 'w toku'
            """
            date_param = dzisiaj.strftime('%Y-%m-%d')
            cursor_plans.execute(suspend_query, (date_param,))
            suspended_count = cursor_plans.rowcount
            conn_plans.commit()
            cursor_plans.close()
            conn_plans.close()
            
            print(f"[ROUTE] ✓ Suspended {suspended_count} active plans for {date_param}")
            
        except Exception as e:
            print(f"[ROUTE] ✗ Error suspending plans: {e}")
        
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
        sekcje = ['Zasyp', 'Workowanie', 'Magazyn', 'Hala Agro']
        
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
                SELECT DISTINCT pw.id, pw.imie_nazwisko
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
                    'rola': 'pracownik'  # Brak kolumny rola w obsada_zmiany
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

@api_bp.route('/pobierz-raport', methods=['GET', 'POST'])
@login_required
@roles_required(['lider', 'admin'])
def pobierz_raport():
    """Pobierz wygenerowany raport (PDF, Excel, TXT)

    Obsługa zarówno POST (formularz) jak i GET (querystring) —
    frontend używa GET w kilku miejscach (window.location.href), więc
    zaakceptujemy oba mechanizmy.
    
    Najpierw próbuje wygenerować raport bezpośrednio z DB (jak /api/zamknij-zmiane-global),
    jeśli się nie powiedzie, próbuje czytać z bazy raporty_koncowe.
    """
    try:
        if request.method == 'POST':
            raport_format = request.form.get('format', 'email')
            data_param = request.form.get('data')
        else:
            raport_format = request.args.get('format', 'email')
            data_param = request.args.get('data')
        
        # Pobierz ostatni raport dla dzisiaj z bazy
        # Pozwól nadpisać datę przez parametr (format YYYY-MM-DD), domyślnie dzisiaj
        if data_param:
            try:
                dzisiaj = datetime.strptime(data_param, '%Y-%m-%d').date()
            except Exception:
                dzisiaj = date.today()
        else:
            dzisiaj = date.today()
        
        # NAJPIERW: Spróbuj wygenerować raport bezpośrednio z DB
        print(f"[POBIERZ-RAPORT] Attempting to generate report for {dzisiaj}")
        try:
            from generator_raportow import generuj_paczke_raportow
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Pobierz uwagi lidera z ostatniego wpisu
            cursor.execute("""
                SELECT lider_uwagi FROM raporty_koncowe
                WHERE data_raportu = %s
                ORDER BY id DESC
                LIMIT 1
            """, (dzisiaj,))
            result = cursor.fetchone()
            uwagi = result[0] if result else ''
            
            conn.close()
            
            lider_name = session.get('zalogowany', 'Nieznany')
            
            xls_path, txt_path, pdf_path = generuj_paczke_raportow(str(dzisiaj), uwagi or '', lider_name)
            print(f"[POBIERZ-RAPORT] Generated: xls={xls_path}, txt={txt_path}, pdf={pdf_path}")
            
            # Zwróć raport w zależy od formatu
            if raport_format == 'email':
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, 200, {
                    'Content-Type': 'text/plain; charset=utf-8',
                    'Content-Disposition': f'attachment; filename="Raport_{dzisiaj}.txt"'
                }
            elif raport_format == 'excel' and xls_path:
                with open(xls_path, 'rb') as f:
                    content = f.read()
                return send_file(
                    BytesIO(content),
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=f'Raport_{dzisiaj}.xlsx'
                )
            elif raport_format == 'pdf' and pdf_path:
                with open(pdf_path, 'rb') as f:
                    content = f.read()
                return send_file(
                    BytesIO(content),
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'Raport_{dzisiaj}.pdf'
                )
            else:
                # Jeśli żaden format nie pasuje, zwróć TXT
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, 200, {
                    'Content-Type': 'text/plain; charset=utf-8',
                    'Content-Disposition': f'attachment; filename="Raport_{dzisiaj}.txt"'
                }
        except Exception as e:
            print(f"[POBIERZ-RAPORT] Generator failed: {e}, falling back to RaportService")
        
        # FALLBACK: Jeśli generator się nie powiedzie, czytaj z bazy
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

# ================= EMAIL CONFIGURATION =================

@api_bp.route('/email-config', methods=['GET'])
@login_required
def get_email_config():
    """
    Endpoint zwracający konfigurację odbiorców raportów email.
    Przydatny dla frontenda aby dynamicznie pobierać listę odbiorców.
    
    Response JSON:
    {
        "recipients": ["osoba1@example.com", "osoba2@example.com"],
        "subject_template": "Raport produkcyjny z dnia {date}",
        "configured": true
    }
    """
    try:
        from config import EMAIL_RECIPIENTS
        
        return jsonify({
            "recipients": EMAIL_RECIPIENTS,
            "subject_template": "Raport produkcyjny z dnia {date}",
            "configured": len(EMAIL_RECIPIENTS) > 0,
            "count": len(EMAIL_RECIPIENTS)
        }), 200
    except Exception as e:
        current_app.logger.error(f"[EMAIL-CONFIG] Błąd pobierania konfiguracji: {e}")
        return jsonify({
            "error": "Błąd pobierania konfiguracji",
            "recipients": [],
            "configured": False
        }), 500


# ================= WZNOWIENIE ZLECEŃ Z POPRZEDNIEGO DNIA =================

@api_bp.route('/wznow_zlecenia_z_wczoraj', methods=['POST'])
@login_required
def wznow_zlecenia_z_wczoraj():
    """
    Endpoint wznawia wszystkie zlecenia ze statusem 'wstrzymane' 
    z poprzedniego dnia (zmieniam status na 'w toku').
    """
    try:
        print(f"[WZNOW-WCZORAJ] Starting auto-resume handler")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-WCZORAJ] Querying for plans from {wczoraj_str}")
        
        # Wznów wszystkie zlecenia w statusie 'wstrzymane' z poprzedniego dnia
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str,))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-WCZORAJ] ✓ Success: Resumed {resumed_count} plans from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "message": f"Wznowiono {resumed_count} zleceń z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-WCZORAJ] ✗ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Błąd przy wznowienia zleceń z poprzedniego dnia"
        }), 500


# ================= RĘCZNE WZNOWIENIE ZLECEŃ DLA SEKCJI =================

@api_bp.route('/wznow_zlecenia_sekcji/<sekcja>', methods=['POST'])
@login_required
def wznow_zlecenia_sekcji(sekcja):
    """
    Endpoint ręcznego wznowienia wszystkich zleceń 'wstrzymane' 
    z poprzedniego dnia dla wybranej sekcji.
    """
    try:
        print(f"[WZNOW-SEKCJA] Starting handler for sekcja={sekcja}")
        
        # Walidacja sekcji
        if sekcja not in ['Zasyp', 'Workowanie', 'Pakowanie', 'Magazyn']:
            print(f"[WZNOW-SEKCJA] ✗ Invalid sekcja: {sekcja}")
            return jsonify({
                "success": False,
                "error": f"Nieznana sekcja: {sekcja}",
                "message": "Sekcja musi być jedną z: Zasyp, Workowanie, Pakowanie, Magazyn"
            }), 400
        
        print(f"[WZNOW-SEKCJA] Sekcja valid: {sekcja}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-SEKCJA] Querying plans from {wczoraj_str} for sekcja={sekcja}")
        
        # Wznów wszystkie zlecenia 'wstrzymane' z poprzedniego dnia dla tej sekcji
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND sekcja = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str, sekcja))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-SEKCJA] ✓ Success: Resumed {resumed_count} plans for sekcja={sekcja} from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "sekcja": sekcja,
            "message": f"✅ Wznowiono {resumed_count} zleceń dla {sekcja} z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-SEKCJA] ✗ Error for sekcja={sekcja}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Błąd przy wznowienia zleceń dla {sekcja}"
        }), 500


# ================= MAGAZYN - AJAX ENDPOINTS =================

@api_bp.route('/edytuj_palete_ajax', methods=['POST'])
@login_required
def edytuj_palete_ajax():
    """Edytuj wagę palet w magazynie via AJAX"""
    try:
        data = request.get_json() or {}
        palete_id = data.get('id')
        nowa_waga = data.get('waga')
        data_powrotu = data.get('data_powrotu') or str(date.today())
        
        if not palete_id or nowa_waga is None:
            return jsonify({"success": False, "message": "Brakuje id lub wagi"}), 400
        
        nowa_waga = float(nowa_waga)
        if nowa_waga <= 0:
            return jsonify({"success": False, "message": "Waga musi być większa od 0"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz plan_id i sekcję palet
        cursor.execute("SELECT plan_id, sekcja FROM palety_workowanie WHERE id=%s", (palete_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Paleta nie znaleziona"}), 404
        
        plan_id, sekcja = result
        
        # Aktualizuj wagę
        cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (nowa_waga, palete_id))
        
        # Przelicz buffer (tonaz_rzeczywisty) dla Workowania
        if sekcja == 'Workowanie':
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
                (plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Paleta edytowana"}), 200
    
    except Exception as e:
        logger = logging.getLogger('werkzeug')
        logger.error(f"Error in edytuj_palete_ajax: {str(e)}")
        return jsonify({"success": False, "message": f"Błąd: {str(e)}"}), 500


@api_bp.route('/usun_palete_ajax', methods=['POST'])
@login_required
def usun_palete_ajax():
    """Usuń paletę z magazynu via AJAX"""
    try:
        data = request.get_json() or {}
        palete_id = data.get('id')
        data_powrotu = data.get('data_powrotu') or str(date.today())
        
        if not palete_id:
            return jsonify({"success": False, "message": "Brakuje id palet"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz plan_id i sekcję palet
        cursor.execute("SELECT plan_id, sekcja FROM palety_workowanie WHERE id=%s", (palete_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Paleta nie znaleziona"}), 404
        
        plan_id, sekcja = result
        
        # Usuń paletę
        cursor.execute("DELETE FROM palety_workowanie WHERE id=%s", (palete_id,))
        
        # Przelicz buffer (tonaz_rzeczywisty) dla Workowania
        if sekcja == 'Workowanie':
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
                (plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Paleta usunięta"}), 200
    
    except Exception as e:
        logger = logging.getLogger('werkzeug')
        logger.error(f"Error in usun_palete_ajax: {str(e)}")
        return jsonify({"success": False, "message": f"Błąd: {str(e)}"}), 500