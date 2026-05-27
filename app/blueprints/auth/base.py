"""Authentication routes and session management.
Handles login, logout, and user-specific interface settings (e.g., bug icon acknowledgment).
"""

from flask import Blueprint, render_template, request, redirect, session, flash, make_response, jsonify, current_app
from datetime import datetime
import time
from werkzeug.security import check_password_hash
import os
import subprocess
import sys

from app.decorators import login_required
from app.db import get_db_connection, ensure_session_tracking_id, touch_active_session, deactivate_active_session
from app.utils.validation import require_field

auth_bp = Blueprint('auth', __name__)


def _printer_server_script_path():
    # os.path.dirname(__file__) is app/blueprints/auth
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    return os.path.join(project_root, 'printer_server', 'server.py')


def _is_printer_server_running():
    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get('https://127.0.0.1:3001/status', timeout=1.5, verify=False)
        return response.status_code == 200
    except Exception:
        return False


def _start_printer_server():
    server_path = _printer_server_script_path()
    if not os.path.exists(server_path):
        return False, f'Nie znaleziono pliku serwera: {server_path}', 404

    if _is_printer_server_running():
        return True, 'Serwer druku juz dziala.', 200

    try:
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = 0x00000010

        process = subprocess.Popen(
            [sys.executable, server_path],
            cwd=os.path.dirname(server_path),
            creationflags=creation_flags,
            start_new_session=True,
        )
        time.sleep(1.2)
        if _is_printer_server_running():
            return True, 'Serwer druku uruchomiony.', 200

        exit_code = process.poll()
        if exit_code is not None:
            return (
                False,
                f'Serwer druku nie uruchomil sie (kod procesu: {exit_code}). Sprawdz zaleznosci i logi.',
                500,
            )

        return (
            False,
            'Serwer druku nie odpowiedzial na porcie 3001 po probie startu. Sprawdz firewall/usluge.',
            500,
        )
    except Exception as error:
        return False, f'Blad startu serwera druku: {error}', 500


def get_user_redirect_target(role, group):
    """Calculate the direct redirect target page based on role and group permissions."""
    normalized_role = (role or '').lower().strip()
    # Resolve numeric roles
    if normalized_role.isdigit():
        roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
        try:
            idx = int(normalized_role)
            if 0 <= idx < len(roles_order):
                normalized_role = roles_order[idx]
        except Exception:
            pass

    role_aliases = {
        'master admin': 'masteradmin',
        'master_admin': 'masteradmin',
        'master-admin': 'masteradmin',
        'laboratorium': 'laborant',
    }
    normalized_role = role_aliases.get(normalized_role, normalized_role)
            
    if normalized_role == 'planista':
        return '/planista'
        
    if normalized_role in ['masteradmin', 'admin', 'lider']:
        return '/'
        
    # For other roles, find their first allowed section
    from app.core.contexts import inject_role_permissions
    role_checker = inject_role_permissions().get('role_has_access')
    
    user_grupa = (group or 'PSD').upper().strip()
    aktywna_linia = user_grupa if user_grupa in ['PSD', 'AGRO'] else 'PSD'
    line_lower = aktywna_linia.lower()
    sections_to_check = ['Zasyp', 'Workowanie', 'Bufor', 'Magazyn']
    
    found_allowed_sec = None
    for sec in sections_to_check:
        page_key = f"{line_lower}.{sec.lower()}"
        if role_checker and role_checker(page_key):
            found_allowed_sec = sec
            break
            
    if found_allowed_sec:
        from flask import url_for
        try:
            return url_for('main.index', sekcja=found_allowed_sec, linia=aktywna_linia)
        except Exception:
            return f"/?sekcja={found_allowed_sec}&linia={aktywna_linia}"
        
    return '/'


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

        try:
            conn = get_db_connection(retries=1)
            cursor = conn.cursor()
        except Exception as e:
            from flask import current_app
            current_app.logger.error("Błąd połączenia z bazą danych podczas logowania: %s", e)
            flash("Błąd połączenia z bazą danych! Sprawdź plik .env lub sieć.", 'danger')
            return redirect('/login')
        
        # Pobierz opcjonalne pole pracownik_id by mapować konto na rekord pracownika
        try:
            cursor.execute("SELECT id, haslo, rola, COALESCE(pracownik_id, NULL), grupa FROM uzytkownicy WHERE login = %s", (login_field,))
            row = cursor.fetchone()
        except Exception as e:
            from flask import current_app
            current_app.logger.error("Błąd zapytania podczas logowania: %s", e)
            cursor.close()
            conn.close()
            flash("Błąd zapytania bazodanowego!", 'danger')
            return redirect('/login')
        
        if row:
            uid, hashed, rola, pracownik_id, grupa = row[0], row[1], row[2], row[3], row[4]
            if hashed and check_password_hash(hashed, password_field):
                # Must set permanent=True to ensure session cookie is saved
                session.permanent = True
                session['zalogowany'] = True
                session['user_id'] = int(uid)
                # Normalize role to lowercase and resolve numeric IDs to string names
                normalized_role = (rola or '').lower().strip()
                if normalized_role.isdigit():
                    roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
                    try:
                        idx = int(normalized_role)
                        if 0 <= idx < len(roles_order):
                            normalized_role = roles_order[idx]
                    except Exception: pass
                
                # Enforce masteradmin role for the MasterAdmin login account to bypass any DB role limitations
                if login_field.lower().strip() == 'masteradmin':
                    normalized_role = 'masteradmin'
                
                session['rola'] = normalized_role
                
                # Admin and Management (Zarzad) must always see everything (PSD + AGRO)
                if normalized_role in ['admin', 'zarzad', 'masteradmin']:
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
                        cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                        p_row = cursor.fetchone()
                        if p_row:
                            imie_nazwisko = p_row[0]
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
                    conn=conn,
                )
                try:
                    conn.commit()
                except Exception:
                    pass
                # record last activity timestamp for server-side inactivity logout
                try:
                    session['last_activity'] = time.time()
                except Exception:
                    pass
                
                cursor.close()
                conn.close()
                
                # Use standard redirect to ensure session cookies are properly handled by all browsers
                target = get_user_redirect_target(session.get('rola'), session.get('grupa'))
                return redirect(target)
        
        cursor.close()
        conn.close()
        flash("Błędne dane!", 'danger')
        return redirect('/login')
    
    # If already logged in, don't show login form — redirect to app
    if session.get('zalogowany'):
        target = get_user_redirect_target(session.get('rola'), session.get('grupa'))
        return redirect(target)
    
    try:
        resp = make_response(render_template('login.html'))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        return resp
    except Exception:
        return render_template('login.html')


def _stop_printer_server():
    if not _is_printer_server_running():
        return True, 'Serwer druku już jest wyłączony.', 200
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        requests.post('https://127.0.0.1:3001/shutdown', timeout=2.0, verify=False)
        return True, 'Serwer druku został wyłączony.', 200
    except requests.exceptions.ReadTimeout:
        # Przekroczenie czasu podczas wyłączania to dobry znak, proces został ubity
        return True, 'Serwer druku został wyłączony.', 200
    except Exception as error:
        return False, f'Błąd zatrzymywania serwera druku: {error}', 500


@auth_bp.route('/api/printer-server/status', methods=['GET'], strict_slashes=False)
def printer_server_status_public():
    """Public status endpoint used by login screen widgets."""
    running = _is_printer_server_running()
    if running:
        return jsonify({'success': True, 'running': True, 'message': 'Serwer druku działa.'})
    return jsonify({'success': True, 'running': False, 'message': 'Serwer druku jest wyłączony.'})


@auth_bp.route('/api/printer-server/start', methods=['POST'], strict_slashes=False)
def start_printer_server_public():
    """Allow starting print server using PIN."""
    payload = request.get_json(silent=True) or request.form or {}
    pin_value = str(payload.get('pin', '')).strip()
    expected_pin = str(os.getenv('PRINTER_SERVER_START_PIN', '0606')).strip()

    if pin_value != expected_pin:
        return jsonify({'success': False, 'message': 'Nieprawidłowy PIN.'}), 403

    success, message, status_code = _start_printer_server()
    try:
        current_app.logger.info('[PRINTER-START-PUBLIC] success=%s, status=%s, ip=%s', success, status_code, request.remote_addr)
    except Exception:
        pass

    return jsonify({'success': success, 'message': message}), status_code


@auth_bp.route('/api/printer-server/stop', methods=['POST'], strict_slashes=False)
def stop_printer_server_public():
    """Allow stopping print server using PIN."""
    payload = request.get_json(silent=True) or request.form or {}
    pin_value = str(payload.get('pin', '')).strip()
    expected_pin = str(os.getenv('PRINTER_SERVER_START_PIN', '0606')).strip()

    if pin_value != expected_pin:
        return jsonify({'success': False, 'message': 'Nieprawidłowy PIN.'}), 403

    success, message, status_code = _stop_printer_server()
    try:
        current_app.logger.info('[PRINTER-STOP-PUBLIC] success=%s, status=%s, ip=%s', success, status_code, request.remote_addr)
    except Exception:
        pass

    return jsonify({'success': success, 'message': message}), status_code


@auth_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    from flask import current_app, make_response
    from app.core.audit import audit_log
    from app.db import deactivate_active_session, deactivate_all_user_sessions
    audit_log('Wylogował się')
    current_app.logger.info("Użytkownik '%s' wylogował się", session.get('login', '—'))
    
    user_id = session.get('user_id')
    if user_id:
        deactivate_all_user_sessions(user_id)
    else:
        deactivate_active_session(session.get('session_tracking_id'))
        
    session.clear()
    resp = make_response(redirect('/login'))
    # No-cache: zapobiega pokazywaniu starych stron z cache po cofnięciu się (mobile BFCache)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    """API endpoint dla beacon-based logout z mobile (navigator.sendBeacon)."""
    from app.core.audit import audit_log
    from app.db import deactivate_active_session, deactivate_all_user_sessions
    try:
        audit_log('Wylogował się (mobile beacon)')
    except Exception:
        pass
    
    user_id = session.get('user_id')
    if user_id:
        deactivate_all_user_sessions(user_id)
    else:
        deactivate_active_session(session.get('session_tracking_id'))
        
    session.clear()
    return jsonify({'success': True, 'redirect': '/login'})


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


