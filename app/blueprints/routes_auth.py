"""Authentication routes and session management.
Handles login, logout, and user-specific interface settings (e.g., bug icon acknowledgment).
"""

from flask import Blueprint, render_template, request, redirect, session, flash, make_response, jsonify
from datetime import datetime
import time
from werkzeug.security import check_password_hash
import os

from app.decorators import login_required
from app.db import get_db_connection, ensure_session_tracking_id, touch_active_session, deactivate_active_session
from app.utils.validation import require_field

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with session management."""
    if request.method == 'POST':
        # Validate required form fields via central helper
        try:
            login_field = require_field(request.form, 'login')
            password_field = require_field(request.form, 'haslo')
        except Exception as e:
            flash(str(e), 'danger')
            return redirect('/login')

        conn = get_db_connection()
        cursor = conn.cursor()
        # Pobierz opcjonalne pole pracownik_id by mapować konto na rekord pracownika
        cursor.execute("SELECT id, haslo, rola, COALESCE(pracownik_id, NULL), grupa FROM uzytkownicy WHERE login = %s", (login_field,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            uid, hashed, rola, pracownik_id, grupa = row[0], row[1], row[2], row[3], row[4]
            if hashed and check_password_hash(hashed, password_field):
                # Must set permanent=True to ensure session cookie is saved
                session.permanent = True
                session['zalogowany'] = True
                session['user_id'] = int(uid)
                # Normalize role to lowercase and resolve numeric IDs to string names
                normalized_role = (rola or '').lower()
                if normalized_role.isdigit():
                    roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
                    try:
                        idx = int(normalized_role)
                        if 0 <= idx < len(roles_order):
                            normalized_role = roles_order[idx]
                    except Exception: pass
                
                session['rola'] = normalized_role
                
                # Admin and Management (Zarzad) must always see everything (PSD + AGRO)
                if normalized_role in ['admin', 'zarzad']:
                    session['grupa'] = 'ALL'
                else:
                    session['grupa'] = (grupa or '').strip()
                # Zapisz login i powiązanie pracownika w sesji (może być None)
                session['login'] = login_field
                session['pracownik_id'] = int(pracownik_id) if pracownik_id is not None else None
                session['session_tracking_id'] = ensure_session_tracking_id(session.get('session_tracking_id'))
                session['show_bug_icon_intro'] = True
                
                # Log login with current process PID
                from flask import current_app
                from app.core.audit import audit_log
                current_app.logger.info("Użytkownik '%s' zalogował się (rola: %s)", login_field, (rola or '').lower())
                audit_log('Zalogował się')
                
                # Pobierz imię_nazwisko z tabeli pracownicy dla wyświetlenia w belce górnej
                imie_nazwisko = None
                if pracownik_id:
                    try:
                        conn2 = get_db_connection()
                        cursor2 = conn2.cursor()
                        cursor2.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                        p_row = cursor2.fetchone()
                        if p_row:
                            imie_nazwisko = p_row[0]
                        cursor2.close()
                        conn2.close()
                    except Exception:
                        pass
                session['imie_nazwisko'] = imie_nazwisko or login_field
                forwarded_for = request.headers.get('X-Forwarded-For', '')
                client_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr)
                touch_active_session(
                    session_id=session.get('session_tracking_id'),
                    user_id=session.get('user_id'),
                    login=login_field,
                    role=session.get('rola'),
                    pracownik_id=session.get('pracownik_id'),
                    display_name=session.get('imie_nazwisko'),
                    last_path=request.path,
                    ip_address=client_ip,
                )
                # record last activity timestamp for server-side inactivity logout
                try:
                    session['last_activity'] = time.time()
                except Exception:
                    pass
                
                # Use standard redirect to ensure session cookies are properly handled by all browsers
                target = '/planista' if rola == 'planista' else '/'
                return redirect(target)
        
        flash("Błędne dane!", 'danger')
        return redirect('/login')
    
    # If already logged in, don't show login form — redirect to app
    if session.get('zalogowany'):
        return redirect('/')
    
    try:
        resp = make_response(render_template('login.html'))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        return resp
    except Exception:
        return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    from flask import current_app
    from app.core.audit import audit_log
    audit_log('Wylogował się')
    current_app.logger.info("Użytkownik '%s' wylogował się", session.get('login', '—'))
    deactivate_active_session(session.get('session_tracking_id'))
    session.clear()
    return redirect('/login')


@auth_bp.route('/zglos')
@login_required
def report_issue():
    """Report an issue with optional section filter."""
    sekcja = request.args.get('sekcja', 'Zasyp')
    now_time = datetime.now().strftime('%H:%M')
    return render_template('report_issue.html', sekcja=sekcja, now_time=now_time)


@auth_bp.route('/moje_zgloszenia_bledow')
@login_required
def my_bug_reports():
    """Show bug reports submitted by the currently logged user."""
    login_value = (session.get('login') or '').strip()
    if not login_value:
        flash('Brak danych użytkownika.', 'warning')
        return redirect('/')

    sort_by = request.args.get('sort', 'id_desc')
    sort_map = {
        'id_desc': 'id DESC',
        'id_asc': 'id ASC',
        'date_desc': 'timestamp DESC',
        'date_asc': 'timestamp ASC',
        'status': 'status ASC, timestamp DESC'
    }
    order_clause = sort_map.get(sort_by, 'id DESC')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    reports = []
    try:
        cursor.execute(
            f"""
            SELECT id, timestamp, opis, sciezka, status, zalaczniki, odpowiedz_admina, odpowiedz_timestamp, odpowiedz_by_login
            FROM zgloszenia_bledow
            WHERE LOWER(login) = LOWER(%s)
            ORDER BY {order_clause}
            LIMIT 200
            """,
            (login_value,)
        )
        reports = cursor.fetchall() or []

        import json
        for report in reports:
            attachments = report.get('zalaczniki')
            if isinstance(attachments, str):
                try:
                    report['zalaczniki'] = json.loads(attachments)
                except Exception:
                    report['zalaczniki'] = []
            elif not attachments:
                report['zalaczniki'] = []
    except Exception:
        flash('Nie udało się pobrać Twoich zgłoszeń.', 'error')
    finally:
        conn.close()

    return render_template('my_bug_reports.html', reports=reports, current_sort=sort_by)


@auth_bp.route('/api/ack_bug_icon_intro', methods=['POST'])
@login_required
def ack_bug_icon_intro():
    """Mark bug-report icon intro as acknowledged for current login session."""
    session['show_bug_icon_intro'] = False
    return jsonify({'success': True})


