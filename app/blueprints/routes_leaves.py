"""Leave request routes (formerly in routes_api.py WNIOSKI O WOLNE section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from app.db import get_db_connection
from app.decorators import login_required, roles_required
import json

leaves_bp = Blueprint('leaves', __name__)

# =============== WNIOSKI O WOLNE ================
@leaves_bp.route('/wnioski/submit', methods=['POST'])
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


@leaves_bp.route('/wnioski/<int:wid>/approve', methods=['POST'])
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


@leaves_bp.route('/wnioski/<int:wid>/reject', methods=['POST'])
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


@leaves_bp.route('/wnioski/day', methods=['GET'])
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


@leaves_bp.route('/wnioski/summary', methods=['GET'])
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


@leaves_bp.route('/panel/wnioski', methods=['GET'])
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


@leaves_bp.route('/panel/planowane', methods=['GET'])
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


@leaves_bp.route('/panel/obecnosci', methods=['GET'])
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


@leaves_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM obecnosc WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@leaves_bp.route('/dodaj_do_obsady', methods=['POST'])
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


@leaves_bp.route('/zapisz_liderow_obsady', methods=['POST'])
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

@leaves_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
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
@leaves_bp.route('/zamknij-zmiane', methods=['GET'])
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

@leaves_bp.route('/zamknij-zmiane-global', methods=['POST', 'GET'])
@login_required
@roles_required('lider', 'admin')
def zamknij_zmiane_global():
    """
    Endpoint to close shift and download reports as ZIP.
    Orchestrates the report generation workflow.
    """
    import sys
    from app.services.report_service import (
        load_shift_notes, 
        get_leader_name, 
        generate_and_download_reports
    )
    
    print("\n[ROUTE] ################# ROUTE HANDLER CALLED #################", file=sys.stderr)
    sys.stderr.flush()
    
    # Parse date from request
    date_str = request.values.get('data') or request.args.get('data')
    if date_str:
        try:
            dzisiaj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            dzisiaj = date.today()
    else:
        dzisiaj = date.today()
    
    date_str = dzisiaj.strftime('%Y-%m-%d')
    
    print("\n" + "="*60)
    print("[ROUTE] /zamknij-zmiane-global called")
    print(f"[ROUTE] Method: {request.method}")
    print(f"[ROUTE] Date: {date_str}")
    print("="*60)
    
    try:
        # Load shift notes
        uwagi = load_shift_notes(dzisiaj)
        
        # Get leader name
        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany')
        }
        form_data = {
            'lider_id': request.form.get('lider_id') or request.values.get('lider_id'),
            'lider_prowadzacy_id': request.form.get('lider_prowadzacy_id') or request.values.get('lider_prowadzacy_id')
        }
        lider_name, uwagi_addition = get_leader_name(session_data, form_data)
        uwagi = (uwagi or '') + uwagi_addition
        
        # Generate reports and create ZIP
        zip_buffer, zip_filename = generate_and_download_reports(date_str, uwagi, lider_name)
        
        # Return ZIP for download
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        print(f"[ROUTE] EXCEPTION CAUGHT IN MAIN HANDLER: {str(e)}", file=sys.stderr)
        sys.stderr.flush()
        print(f"[ROUTE] ERROR {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'ERROR Blad przy generowaniu raportow: {str(e)}', 'error')
        print("="*60 + "\n")
        return redirect('/')


@leaves_bp.route('/obsada-for-date')
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


@leaves_bp.route('/zapisz-raport-koncowy', methods=['POST'])
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

@leaves_bp.route('/zapisz-raport-koncowy-global', methods=['POST'])
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

@leaves_bp.route('/pobierz-raport', methods=['GET', 'POST'])
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


