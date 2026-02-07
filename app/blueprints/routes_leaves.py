"""Leave request routes (formerly in routes_api.py WNIOSKI O WOLNE section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from datetime import date, datetime, timedelta
from app.db import get_db_connection
from app.decorators import login_required, roles_required
from app.services.leave_request_service import LeaveRequestService
from app.services.attendance_service import AttendanceService
from io import BytesIO
import json

leaves_bp = Blueprint('leaves', __name__)

def bezpieczny_powrot():
    """Return to appropriate view based on user role and context."""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('index', sekcja=sekcja, data=data)

# =============== WNIOSKI O WOLNE ================
@leaves_bp.route('/wnioski/submit', methods=['POST'])
@login_required
def submit_wniosek():
    """Submit leave request - delegated to LeaveRequestService."""
    pracownik_id = session.get('pracownik_id') or request.form.get('pracownik_id')
    if not pracownik_id:
        flash('Brak przypisanego pracownika do konta.', 'warning')
        return redirect(bezpieczny_powrot())
    
    typ = request.form.get('typ') or 'Urlop'
    data_od_str = request.form.get('data_od')
    data_do_str = request.form.get('data_do')
    czas_od = request.form.get('czas_od') or None
    czas_do = request.form.get('czas_do') or None
    powod = request.form.get('powod') or ''
    
    try:
        data_od = datetime.strptime(data_od_str, '%Y-%m-%d').date() if data_od_str else None
        data_do = datetime.strptime(data_do_str, '%Y-%m-%d').date() if data_do_str else None
    except Exception:
        flash('Nieprawidłowy format daty.', 'warning')
        return redirect(bezpieczny_powrot())
    
    success, message, _ = LeaveRequestService.submit_leave_request(
        pracownik_id=int(pracownik_id),
        typ=typ,
        data_od=data_od,
        data_do=data_do,
        czas_od=czas_od,
        czas_do=czas_do,
        powod=powod
    )
    
    flash(message, 'success' if success else 'warning')
    return redirect(url_for('moje_godziny'))


@leaves_bp.route('/wnioski/<int:wid>/approve', methods=['POST'])
@roles_required('lider', 'admin')
def approve_wniosek(wid):
    """Approve leave request - delegated to LeaveRequestService."""
    lider_id = session.get('pracownik_id')
    success, message = LeaveRequestService.approve_leave_request(wid, lider_id)
    
    flash(message, 'success' if success else 'warning')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify({'success': success, 'message': message})
    return redirect(bezpieczny_powrot())


@leaves_bp.route('/wnioski/<int:wid>/reject', methods=['POST'])
@roles_required('lider', 'admin')
def reject_wniosek(wid):
    """Reject leave request - delegated to LeaveRequestService."""
    lider_id = session.get('pracownik_id')
    success, message = LeaveRequestService.reject_leave_request(wid, lider_id)
    
    flash(message, 'info' if success else 'warning')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify({'success': success, 'message': message})
    return redirect(bezpieczny_powrot())


@leaves_bp.route('/wnioski/day', methods=['GET'])
@roles_required('lider', 'admin')
def wnioski_for_day():
    """Get leave requests for specific employee and date - delegated to LeaveRequestService."""
    pracownik_id = request.args.get('pracownik_id')
    date_str = request.args.get('date')
    
    if not pracownik_id or not date_str:
        return jsonify({'error': 'missing parameters'}), 400
    
    result = LeaveRequestService.get_requests_for_day(int(pracownik_id), date_str)
    
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@leaves_bp.route('/wnioski/summary', methods=['GET'])
@login_required
def wnioski_summary():
    """Get leave summary and hours summary for employee - delegated to LeaveRequestService."""
    pracownik_id = request.args.get('pracownik_id') or session.get('pracownik_id')
    
    if not pracownik_id:
        return jsonify({'error': 'missing pracownik_id'}), 400
    
    try:
        pracownik_id = int(pracownik_id)
    except Exception:
        return jsonify({'error': 'invalid pracownik_id'}), 400
    
    result = LeaveRequestService.get_summary_for_employee(pracownik_id)
    
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@leaves_bp.route('/panel/wnioski', methods=['GET'])
@roles_required('lider', 'admin')
def panel_wnioski():
    """Get pending leave requests panel - delegated to AttendanceService."""
    return AttendanceService.get_pending_requests_panel()


@leaves_bp.route('/panel/planowane', methods=['GET'])
@login_required
def panel_planowane():
    """Get planned leaves panel for next 60 days - delegated to AttendanceService."""
    return AttendanceService.get_planned_leaves_panel()


@leaves_bp.route('/panel/obecnosci', methods=['GET'])
@login_required
def panel_obecnosci():
    """Get recent absences panel for last 30 days - delegated to AttendanceService."""
    return AttendanceService.get_recent_absences_panel()


@leaves_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id):
    """Delete absence record - delegated to AttendanceService."""
    success = AttendanceService.delete_absence_record(id)
    
    if not success:
        flash('Błąd przy usuwaniu wpisu.', 'warning')
    else:
        flash('Wpis usunięty.', 'success')
    
    return redirect(bezpieczny_powrot())


@leaves_bp.route('/dodaj_do_obsady', methods=['POST'])
@login_required
def dodaj_do_obsady():
    """Add employee to schedule - delegated to AttendanceService."""
    sekcja = request.form.get('sekcja')
    pracownik_id = request.form.get('pracownik_id')
    date_str = request.form.get('date') or request.args.get('date')
    
    if not sekcja or not pracownik_id:
        flash('Brak wybranego pracownika lub sekcji.', 'warning')
        return redirect(bezpieczny_powrot())
    
    success, inserted_id, employee_name = AttendanceService.add_to_schedule(sekcja, int(pracownik_id), date_str)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': success, 'id': inserted_id, 'pracownik_id': pracownik_id, 'name': employee_name})
    
    if success:
        flash(f'Pracownik {employee_name} dodany do obsady.', 'success')
    else:
        flash('Błąd przy dodawaniu do obsady.', 'warning')
    
    return redirect(bezpieczny_powrot())


@leaves_bp.route('/zapisz_liderow_obsady', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_liderow_obsady():
    """Save shift leaders - delegated to AttendanceService."""
    date_str = request.form.get('date') or request.args.get('date')
    lider_psd = request.form.get('lider_psd') or None
    lider_agro = request.form.get('lider_agro') or None
    
    success = AttendanceService.save_shift_leaders(date_str, lider_psd, lider_agro)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': success})
    
    if success:
        flash('Liderzy zmianki zapisani.', 'success')
    else:
        flash('Błąd przy zapisywaniu liderów.', 'warning')
    
    return redirect(bezpieczny_powrot())


@leaves_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id):
    """Remove employee from schedule - delegated to AttendanceService."""
    success = AttendanceService.remove_from_schedule(id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': success})
    
    if success:
        flash('Pracownik usunięty z obsady.', 'success')
    else:
        flash('Błąd przy usuwaniu z obsady.', 'warning')
    
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
    """Get schedule (obsada) for specified date."""
    date_str = request.args.get('date')
    
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
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
        rows = [{'sekcja': r[0], 'id': r[1], 'imie_nazwisko': r[2]} for r in cursor.fetchall()]
        conn.close()
        return jsonify({'date': qdate.isoformat(), 'rows': rows})
    except Exception as e:
        current_app.logger.exception('obsada_for_date error')
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
            from app.generator_raportow import generuj_paczke_raportow
            
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


