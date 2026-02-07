from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
import os
import glob
from datetime import date, datetime
from app.db import get_db_connection, rollover_unfinished
from app.decorators import login_required, roles_required

production_bp = Blueprint('production', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data)


@production_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    """Rozpocznij wykonywanie zlecenia (zmiana statusu na 'w toku')
    
    Workowanie może startować niezależnie - Zasyp to przygotowanie wsadu,
    Workowanie workuje z bufora. Jeśli na Zasyp jest inne zlecenie - pokaż info.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status, COALESCE(tonaz_rzeczywisty, 0) FROM plan_produkcji WHERE id=%s", (id,))
    z = cursor.fetchone()
    
    warning_info = None  # Informacja o tym co dzieje się na Zasyp
    
    if z:
        produkt, tonaz, sekcja, data_planu, typ, status_obecny, tonaz_rzeczywisty_zasyp = z
        
        # INFO ONLY (nie blokuje): jeśli na Workowanie, sprawdzić co dzieje się na Zasyp
        if sekcja == 'Workowanie':
            cursor.execute(
                "SELECT id, produkt FROM plan_produkcji "
                "WHERE sekcja='Zasyp' AND status='w toku' AND DATE(data_planu)=%s LIMIT 1",
                (data_planu,)
            )
            active_on_zasyp = cursor.fetchone()
            
            if active_on_zasyp and active_on_zasyp[0] != id:
                # Inne zlecenie aktywne na Zasyp - informuj ale nie blokuj
                warning_info = {
                    'message': f"Na Zasyp trwa zlecenie: <strong>{active_on_zasyp[1]}</strong>",
                    'zasyp_order_id': active_on_zasyp[0],
                    'zasyp_order_name': active_on_zasyp[1]
                }
        
        # Zawsze wykonaj START - Workowanie pracuje niezależnie z bufora
        if status_obecny != 'w toku':
            cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
            cursor.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW(), real_stop=NULL WHERE id=%s", (id,))
            flash(f"✅ Uruchomiono: <strong>{produkt}</strong>", 'success')
            
            # Jeśli jest warning info - dodaj do flash message
            if warning_info:
                flash(f"ℹ️ {warning_info['message']}", 'info')
        
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@production_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    """Zakończ wykonywanie zlecenia"""
    conn = get_db_connection()
    cursor = conn.cursor()
    final_tonaz = request.form.get('final_tonaz')
    wyjasnienie = request.form.get('wyjasnienie')
    uszkodzone_worki = request.form.get('uszkodzone_worki')
    sekcja = request.form.get('sekcja')
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
    if uszkodzone_worki and sekcja == 'Workowanie':
        try:
            uszkodzone_count = int(uszkodzone_worki)
            sql += ", uszkodzone_worki=%s"
            params.append(uszkodzone_count)
        except (ValueError, TypeError):
            pass
    sql += " WHERE id=%s"
    params.append(id)
    cursor.execute(sql, tuple(params))
    
    # Zasyp i Workowanie działają NIEZALEŻNIE
    # Brak automatycznego aktualizowania Workowania gdy kończy się Zasyp
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@production_bp.route('/zapisz_wyjasnienie/<int:id>', methods=['POST'])
@login_required
def zapisz_wyjasnienie(id):
    """Zapisz wyjaśnienie rozbieżności"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji SET wyjasnienie_rozbieznosci=%s WHERE id=%s", (request.form.get('wyjasnienie'), id))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@production_bp.route('/koniec_zlecenie_page/<int:id>', methods=['GET'])
@login_required
def koniec_zlecenie_page(id):
    """Render confirmation fragment for ending job order"""
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Zasyp'))
    produkt = None
    tonaz_rzeczywisty = None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT produkt, tonaz_rzeczywisty FROM plan_produkcji WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            produkt, tonaz_rzeczywisty = row[0], row[1]
    except Exception:
        try: current_app.logger.exception('Failed to fetch plan %s for koniec_zlecenie_page', id)
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass

    return render_template('koniec_zlecenie.html', id=id, sekcja=sekcja, produkt=produkt, tonaz=tonaz_rzeczywisty)


@production_bp.route('/test-pobierz-raport', methods=['GET'])
@login_required
def api_test_pobierz_raport():
    """Test endpoint: return most recent file from raporty/ directory as attachment"""
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


@production_bp.route('/szarza_page/<int:plan_id>', methods=['GET'])
@login_required
def szarza_page(plan_id):
    """Render form to add a szarża (charge) for Zasyp plan"""
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


@production_bp.route('/wyjasnij_page/<int:id>', methods=['GET'])
@login_required
def wyjasnij_page(id):
    """Render form to submit explanation via zapisz_wyjasnienie"""
    return render_template('wyjasnij.html', id=id)


@production_bp.route('/manual_rollover', methods=['POST'])
@roles_required('lider', 'admin')
def manual_rollover():
    """Manually rollover unfinished jobs from one date to another"""
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


@production_bp.route('/obsada_page', methods=['GET'])
@login_required
def obsada_page():
    """Render slide-over for managing obsada (workers on shift) for a sekcja"""
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
        # pełna lista pracowników (dla wyboru liderów) - tylko liderzy
        cursor.execute("SELECT p.id, p.imie_nazwisko FROM pracownicy p JOIN uzytkownicy u ON p.id = u.pracownik_id WHERE u.rola='lider' ORDER BY p.imie_nazwisko")
        all_pracownicy = cursor.fetchall()
        # pobierz liderów dla tej daty (jeśli istnieją)
        cursor.execute("SELECT lider_psd_id, lider_agro_id FROM obsada_liderzy WHERE data_wpisu=%s", (qdate,))
        lider_row = cursor.fetchone()
        lider_psd_id = lider_row[0] if lider_row else None
        lider_agro_id = lider_row[1] if lider_row else None
    finally:
        try: conn.close()
        except Exception: pass

    # If requested via AJAX, return only the fragment
    try:
        is_ajax = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'
    except Exception:
        is_ajax = False

    if is_ajax:
        return render_template('obsada_fragment.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)

    return render_template('obsada.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)


