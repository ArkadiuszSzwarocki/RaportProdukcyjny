"""Authentication routes and session management.
Handles login, logout, and user-specific interface settings (e.g., bug icon acknowledgment).
"""

from flask import Blueprint, render_template, request, redirect, session, flash, make_response, jsonify, current_app
from datetime import datetime
import time
from werkzeug.security import check_password_hash
import os
import socket
import subprocess
import sys
from urllib.parse import urlparse

from app.decorators import login_required
from app.db import get_db_connection, ensure_session_tracking_id, touch_active_session, deactivate_active_session
from app.utils.validation import require_field

auth_bp = Blueprint('auth', __name__)


def _project_root_path():
    # os.path.dirname(__file__) is app/blueprints/auth
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


def _printer_server_script_path():
    project_root = _project_root_path()
    return os.path.join(project_root, 'printer_server', 'server.py')


def _printer_server_start_log_path():
    return os.path.join(_project_root_path(), 'logs', 'printer_server_start.log')


def _printer_server_subprocess_env():
    # Flask dev reloader injects socket-related env vars used only by the main app.
    # If inherited by the print bridge subprocess on Windows, Werkzeug can crash with WinError 10038.
    env = os.environ.copy()
    env.pop('WERKZEUG_SERVER_FD', None)
    env.pop('WERKZEUG_RUN_MAIN', None)
    return env


def _tail_text_file(path, max_lines=8):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()
        return ''.join(lines[-max_lines:]).strip()
    except Exception:
        return ''


def _is_port_open(host='127.0.0.1', port=3001, timeout=0.35):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _bridge_base_candidates():
    base_value = str(os.getenv('PRINTER_BRIDGE_URL', 'https://127.0.0.1:3001') or '').strip().rstrip('/')
    if not base_value:
        base_value = 'https://127.0.0.1:3001'

    lowered = base_value.lower()
    if lowered.endswith('/drukuj-zpl'):
        base_value = base_value[:-11]
    elif lowered.endswith('/status'):
        base_value = base_value[:-7]

    if '://' not in base_value:
        base_value = f'https://{base_value}'

    candidates = []

    def _append(candidate):
        value = str(candidate or '').strip().rstrip('/')
        if not value:
            return
        if value.lower() in {item.lower() for item in candidates}:
            return
        candidates.append(value)

    _append(base_value)

    parsed = urlparse(base_value)
    scheme = (parsed.scheme or '').lower()
    if scheme in ('http', 'https'):
        alt_scheme = 'http' if scheme == 'https' else 'https'
        _append(f"{alt_scheme}://{parsed.netloc}{parsed.path or ''}")

    return candidates


def _bridge_target_is_localhost():
    candidates = _bridge_base_candidates()
    if not candidates:
        return False
    parsed = urlparse(candidates[0])
    host = (parsed.hostname or '').strip().lower()
    return host in ('127.0.0.1', 'localhost', '::1')


def _request_bridge(method, path, timeout):
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    normalized_path = '/' + str(path or '').lstrip('/')
    last_error = None
    for bridge_base in _bridge_base_candidates():
        try:
            response = requests.request(
                method,
                f"{bridge_base}{normalized_path}",
                timeout=timeout,
                verify=False,
            )
            return response
        except Exception as error:
            last_error = error
            continue

    if last_error:
        raise last_error
    raise RuntimeError('Brak skonfigurowanego endpointu mostka druku.')


def _is_printer_server_running():
    try:
        response = _request_bridge('GET', '/status', timeout=(0.5, 1.2))
        return response.status_code == 200
    except Exception:
        return False


def _start_printer_server():
    server_path = _printer_server_script_path()
    if not os.path.exists(server_path):
        return False, f'Nie znaleziono pliku serwera: {server_path}', 404

    if not _bridge_target_is_localhost():
        return (
            False,
            'Start lokalny pominięty: PRINTER_BRIDGE_URL wskazuje zdalny mostek druku.',
            400,
        )

    if _is_printer_server_running():
        return True, 'Serwer druku juz dziala.', 200

    if _is_port_open('127.0.0.1', 3001):
        return (
            False,
            'Port 3001 jest już zajęty przez inny proces. Zwolnij port i uruchom serwer druku ponownie.',
            500,
        )

    try:
        creation_flags = 0
        show_console = str(os.getenv('PRINTER_SERVER_SHOW_CONSOLE', 'false')).strip().lower() in ('1', 'true', 'yes')
        if os.name == 'nt' and show_console:
            creation_flags = 0x00000010

        log_path = _printer_server_start_log_path()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, 'a', encoding='utf-8', errors='replace') as startup_log:
            startup_log.write(
                f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] START request pid={os.getpid()} exe={sys.executable}\n"
            )
            startup_log.flush()

            process = subprocess.Popen(
                [sys.executable, server_path],
                cwd=os.path.dirname(server_path),
                creationflags=creation_flags,
                start_new_session=True,
                env=_printer_server_subprocess_env(),
                stdout=startup_log,
                stderr=subprocess.STDOUT,
            )

        deadline = time.time() + 6.0
        while time.time() < deadline:
            if _is_printer_server_running():
                return True, 'Serwer druku uruchomiony.', 200

            exit_code = process.poll()
            if exit_code is not None:
                startup_tail = _tail_text_file(log_path, max_lines=10)
                if startup_tail:
                    startup_tail = startup_tail.replace('\r', ' ').replace('\n', ' | ')
                    return (
                        False,
                        f'Serwer druku nie uruchomil sie (kod procesu: {exit_code}). Log: {startup_tail}',
                        500,
                    )
                return (
                    False,
                    f'Serwer druku nie uruchomil sie (kod procesu: {exit_code}). Sprawdz log: {log_path}',
                    500,
                )

            time.sleep(0.35)

        if _is_port_open('127.0.0.1', 3001):
            return (
                False,
                'Port 3001 odpowiada, ale endpoint /status (HTTP/HTTPS) nie jest dostępny. Możliwy konflikt usługi na porcie 3001.',
                500,
            )

        return (
            False,
            f'Serwer druku nie odpowiedzial na porcie 3001 po probie startu. Sprawdz log: {log_path}',
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

    if not _bridge_target_is_localhost():
        return False, 'Zatrzymywanie zdalnego mostka jest zablokowane z poziomu tego panelu.', 400

    try:
        _request_bridge('POST', '/shutdown', timeout=2.0)
        return True, 'Serwer druku został wyłączony.', 200
    except Exception as error:
        # Jeśli serwer rzeczywiście się wyłączył (nie odpowiada już na status), traktujemy to jako sukces.
        # Jest to częste, gdy proces zabija się natychmiast i gwałtownie zrywa połączenie TCP (np. błąd 10054).
        time.sleep(0.5)
        if not _is_printer_server_running():
            return True, 'Serwer druku został wyłączony.', 200
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
        current_app.logger.info(
            '[PRINTER-START-PUBLIC] success=%s, status=%s, ip=%s, message=%s',
            success,
            status_code,
            request.remote_addr,
            message,
        )
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
        current_app.logger.info(
            '[PRINTER-STOP-PUBLIC] success=%s, status=%s, ip=%s, message=%s',
            success,
            status_code,
            request.remote_addr,
            message,
        )
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


