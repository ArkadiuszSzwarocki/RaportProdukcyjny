"""Authentication routes and session management.
Handles login, logout, and user-specific interface settings.
"""

from datetime import datetime
import hmac
import os
import socket
import subprocess
import sys
import time

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.security_hardening import current_client_ip
from app.decorators import login_required
from app.db import (
    deactivate_active_session,
    ensure_session_tracking_id,
    get_db_connection,
    touch_active_session,
)
from app.utils.validation import require_field


auth_bp = Blueprint('auth', __name__)


def _project_root_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


def _printer_server_script_path():
    return os.path.join(_project_root_path(), 'printer_server', 'server.py')


def _printer_server_start_log_path():
    return os.path.join(_project_root_path(), 'logs', 'printer_server_start.log')


def _printer_server_subprocess_env():
    env = os.environ.copy()
    env.pop('WERKZEUG_SERVER_FD', None)
    env.pop('WERKZEUG_RUN_MAIN', None)
    return env


def _tail_text_file(path, max_lines=8):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            return ''.join(handle.readlines()[-max_lines:]).strip()
    except Exception:
        return ''


def _is_port_open(host='127.0.0.1', port=3001, timeout=0.35):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _bridge_target_is_localhost():
    from app.services.print_server import get_printer

    return get_printer()._is_local_bridge_target()  # pylint: disable=protected-access


def _request_bridge(method, path, timeout):
    """Use the single authenticated bridge client with TLS verification enabled."""
    from app.services.print_server import get_printer

    response, _ = get_printer()._request_bridge(  # pylint: disable=protected-access
        method,
        path,
        timeout=timeout,
    )
    return response


def _is_printer_server_running():
    from app.services.print_server import get_printer

    ok, _ = get_printer().test_connection()
    return bool(ok)


def _start_printer_server():
    server_path = _printer_server_script_path()
    if not os.path.exists(server_path):
        return False, f'Nie znaleziono pliku serwera: {server_path}', 404

    if not _bridge_target_is_localhost():
        return False, 'Start lokalny pominięty: PRINTER_BRIDGE_URL wskazuje zdalny mostek druku.', 400

    if _is_printer_server_running():
        return True, 'Serwer druku juz dziala.', 200

    if _is_port_open('127.0.0.1', 3001):
        return False, 'Port 3001 jest już zajęty przez inny proces.', 500

    try:
        creation_flags = 0
        show_console = str(os.getenv('PRINTER_SERVER_SHOW_CONSOLE', 'false')).strip().lower() in ('1', 'true', 'yes')
        if os.name == 'nt' and show_console:
            creation_flags = 0x00000010

        log_path = _printer_server_start_log_path()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'a', encoding='utf-8', errors='replace') as startup_log:
            startup_log.write(
                f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] START request "
                f"pid={os.getpid()} exe={sys.executable}\n"
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
                    return False, f'Serwer druku nie uruchomil sie (kod {exit_code}). Log: {startup_tail}', 500
                return False, f'Serwer druku nie uruchomil sie (kod procesu: {exit_code}).', 500
            time.sleep(0.35)

        return False, f'Serwer druku nie odpowiedzial po starcie. Sprawdz log: {log_path}', 500
    except Exception as error:
        return False, f'Blad startu serwera druku: {error}', 500


def get_user_redirect_target(role, group):
    """Calculate the direct redirect target page based on role and group permissions."""
    normalized_role = (role or '').lower().strip()
    if normalized_role.isdigit():
        roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
        try:
            idx = int(normalized_role)
            if 0 <= idx < len(roles_order):
                normalized_role = roles_order[idx]
        except (TypeError, ValueError):
            pass

    role_aliases = {
        'master admin': 'masteradmin',
        'master_admin': 'masteradmin',
        'master-admin': 'masteradmin',
        'laboratorium': 'laborant',
    }
    normalized_role = role_aliases.get(normalized_role, normalized_role)
    normalized_group = (group or '').upper().strip()

    if normalized_group == 'OSIP':
        return '/osip/transfers'
    if normalized_role == 'planista':
        return '/planista'
    return '/agro/scanner/ui'


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with DB-backed roles and rate limiting."""
    if request.method == 'POST':
        try:
            login_field = require_field(request.form, 'login')
            password_field = require_field(request.form, 'haslo')
        except Exception as exc:
            flash(str(exc), 'danger')
            return redirect('/login')

        from app.services.login_rate_limiter_service import login_rate_limiter

        client_ip = current_client_ip()
        is_limited, remaining_sec = login_rate_limiter.is_rate_limited(client_ip, login_field)
        if is_limited:
            from app.core.audit import security_audit_log

            security_audit_log(
                'RATE_LIMIT_LOCKOUT',
                f'Lockout={remaining_sec}s',
                user_login=login_field,
                client_ip=client_ip,
            )
            flash(
                f'Zbyt wiele nieudanych prób logowania. Odczekaj {remaining_sec} sekund przed kolejną próbą.',
                'danger',
            )
            return redirect('/login')

        try:
            conn = get_db_connection(retries=1)
            cursor = conn.cursor()
        except Exception as exc:
            current_app.logger.error('Błąd połączenia z bazą danych podczas logowania: %s', exc)
            flash('Błąd połączenia z bazą danych!', 'danger')
            return redirect('/login')

        try:
            cursor.execute(
                'SELECT id, haslo, rola, COALESCE(pracownik_id, NULL), grupa '
                'FROM uzytkownicy WHERE login = %s',
                (login_field,),
            )
            row = cursor.fetchone()
        except Exception as exc:
            current_app.logger.error('Błąd zapytania podczas logowania: %s', exc)
            cursor.close()
            conn.close()
            flash('Błąd zapytania bazodanowego!', 'danger')
            return redirect('/login')

        if row:
            uid, hashed, rola, pracownik_id, grupa = row[0], row[1], row[2], row[3], row[4]
            if hashed and check_password_hash(hashed, password_field):
                login_rate_limiter.reset_attempts(client_ip, login_field)
                session.clear()
                session.permanent = True
                session['zalogowany'] = True
                session['user_id'] = int(uid)

                normalized_role = (rola or '').lower().strip()
                if normalized_role.isdigit():
                    roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
                    try:
                        idx = int(normalized_role)
                        if 0 <= idx < len(roles_order):
                            normalized_role = roles_order[idx]
                    except (TypeError, ValueError):
                        pass

                # Never derive privileged roles from the username. The DB record
                # is the source of truth and middleware periodically revalidates it.
                session['rola'] = normalized_role
                if normalized_role in ['admin', 'zarzad', 'masteradmin', 'lider']:
                    session['grupa'] = 'ALL'
                else:
                    session['grupa'] = (grupa or '').strip()

                session['login'] = login_field
                session['pracownik_id'] = int(pracownik_id) if pracownik_id is not None else None
                session['session_tracking_id'] = ensure_session_tracking_id(None)
                session['show_bug_icon_intro'] = True

                from app.core.audit import audit_log, security_audit_log

                audit_log('Zalogował się')
                security_audit_log(
                    'LOGIN_SUCCESS',
                    f'Role={normalized_role}, Hall={session.get("grupa")}',
                    user_login=login_field,
                    client_ip=client_ip,
                )

                imie_nazwisko = None
                if pracownik_id:
                    try:
                        cursor.execute('SELECT imie_nazwisko FROM pracownicy WHERE id = %s', (pracownik_id,))
                        p_row = cursor.fetchone()
                        if p_row:
                            imie_nazwisko = p_row[0]
                    except Exception:
                        pass
                session['imie_nazwisko'] = imie_nazwisko or login_field

                touch_active_session(
                    session_id=session['session_tracking_id'],
                    user_id=session['user_id'],
                    login=login_field,
                    role=session['rola'],
                    pracownik_id=session.get('pracownik_id'),
                    display_name=session['imie_nazwisko'],
                    last_path=request.path,
                    ip_address=client_ip,
                    conn=conn,
                )
                conn.commit()
                now_ts = time.time()
                session['last_activity'] = now_ts
                session['last_session_active_check'] = now_ts
                session['session_active_cached'] = True
                session['accepted_concurrent_ts'] = now_ts
                cursor.close()
                conn.close()
                return redirect(get_user_redirect_target(session.get('rola'), session.get('grupa')))

        is_now_locked, lock_duration = login_rate_limiter.record_failed_attempt(client_ip, login_field)
        cursor.close()
        conn.close()
        from app.core.audit import security_audit_log

        security_audit_log(
            'FAILED_LOGIN',
            f'RateLimitLocked={is_now_locked}',
            user_login=login_field,
            client_ip=client_ip,
        )
        if is_now_locked:
            flash(f'Zbyt wiele nieudanych prób logowania. Blokada: {lock_duration} sekund.', 'danger')
        else:
            flash('Błędne dane logowania!', 'danger')
        return redirect('/login')

    if session.get('zalogowany'):
        return redirect(get_user_redirect_target(session.get('rola'), session.get('grupa')))

    response = make_response(render_template('login.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


def _stop_printer_server():
    if not _is_printer_server_running():
        return True, 'Serwer druku już jest wyłączony.', 200
    if not _bridge_target_is_localhost():
        return False, 'Zatrzymywanie zdalnego mostka jest zablokowane.', 400
    try:
        response = _request_bridge('POST', '/shutdown', timeout=2.0)
        if response.status_code not in (200, 202):
            return False, f'Mostek odmówił zatrzymania (HTTP {response.status_code}).', response.status_code
        return True, 'Serwer druku został wyłączony.', 200
    except Exception as error:
        time.sleep(0.5)
        if not _is_printer_server_running():
            return True, 'Serwer druku został wyłączony.', 200
        return False, f'Błąd zatrzymywania serwera druku: {error}', 500


def _printer_control_pin_ok(pin_value):
    expected_pin = str(os.getenv('PRINTER_SERVER_START_PIN', '')).strip()
    if not expected_pin:
        return False, 503, 'Sterowanie PIN-em nie jest skonfigurowane.'

    from app.services.login_rate_limiter_service import login_rate_limiter

    client_ip = current_client_ip()
    limiter_key = '__printer_bridge_control__'
    limited, remaining = login_rate_limiter.is_rate_limited(client_ip, limiter_key)
    if limited:
        return False, 429, f'Zbyt wiele prób. Odczekaj {remaining} sekund.'

    if not hmac.compare_digest(str(pin_value or '').strip(), expected_pin):
        login_rate_limiter.record_failed_attempt(client_ip, limiter_key)
        return False, 403, 'Nieprawidłowy PIN.'

    login_rate_limiter.reset_attempts(client_ip, limiter_key)
    return True, 200, ''


@auth_bp.route('/api/printer-server/status', methods=['GET'], strict_slashes=False)
def printer_server_status_public():
    running = _is_printer_server_running()
    return jsonify({
        'success': True,
        'running': running,
        'message': 'Serwer druku działa.' if running else 'Serwer druku jest wyłączony.',
    })


@auth_bp.route('/api/printer-server/start', methods=['POST'], strict_slashes=False)
def start_printer_server_public():
    payload = request.get_json(silent=True) or request.form or {}
    pin_ok, error_status, error_message = _printer_control_pin_ok(payload.get('pin'))
    if not pin_ok:
        return jsonify({'success': False, 'message': error_message}), error_status
    success, message, status_code = _start_printer_server()
    return jsonify({'success': success, 'message': message}), status_code


@auth_bp.route('/api/printer-server/stop', methods=['POST'], strict_slashes=False)
def stop_printer_server_public():
    payload = request.get_json(silent=True) or request.form or {}
    pin_ok, error_status, error_message = _printer_control_pin_ok(payload.get('pin'))
    if not pin_ok:
        return jsonify({'success': False, 'message': error_message}), error_status
    success, message, status_code = _stop_printer_server()
    return jsonify({'success': success, 'message': message}), status_code


@auth_bp.route('/logout')
def logout():
    from app.core.audit import audit_log

    audit_log('Wylogował się')
    deactivate_active_session(session.get('session_tracking_id'))
    session.clear()
    response = make_response(redirect('/login'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    from app.core.audit import audit_log

    try:
        audit_log('Wylogował się (mobile beacon)')
    except Exception:
        pass
    deactivate_active_session(session.get('session_tracking_id'))
    session.clear()
    return jsonify({'success': True, 'redirect': '/login'})


@auth_bp.route('/zglos')
@login_required
def report_issue():
    return render_template('report_issue.html')


@auth_bp.route('/moje_zgloszenia_bledow')
@login_required
def my_bug_reports():
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
        'status': 'status ASC, timestamp DESC',
    }
    order_clause = sort_map.get(sort_by, 'id DESC')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    reports = []
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zgloszenia_bledow_odpowiedzi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                zgloszenie_id BIGINT NOT NULL,
                autor_login VARCHAR(50) NOT NULL,
                tresc TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_zgloszenie_id (zgloszenie_id)
            )
        """)
        try:
            cursor.execute("""
                INSERT INTO zgloszenia_bledow_odpowiedzi (zgloszenie_id, autor_login, tresc, created_at)
                SELECT b.id, COALESCE(b.odpowiedz_by_login, 'admin'), b.odpowiedz_admina,
                       COALESCE(b.odpowiedz_timestamp, b.timestamp)
                FROM zgloszenia_bledow b
                WHERE b.odpowiedz_admina IS NOT NULL AND TRIM(b.odpowiedz_admina) <> ''
                  AND NOT EXISTS (
                      SELECT 1 FROM zgloszenia_bledow_odpowiedzi r
                      WHERE r.zgloszenie_id = b.id AND r.tresc = b.odpowiedz_admina
                  )
            """)
        except Exception:
            pass

        cursor.execute(
            f"""SELECT id, timestamp, opis, sciezka, status, zalaczniki,
                       odpowiedz_admina, odpowiedz_timestamp, odpowiedz_by_login
                FROM zgloszenia_bledow
                WHERE LOWER(login) = LOWER(%s)
                ORDER BY {order_clause}
                LIMIT 200""",
            (login_value,),
        )
        reports = cursor.fetchall() or []

        if reports:
            report_ids = [report['id'] for report in reports]
            placeholders = ','.join(['%s'] * len(report_ids))
            cursor.execute(
                f'SELECT * FROM zgloszenia_bledow_odpowiedzi '
                f'WHERE zgloszenie_id IN ({placeholders}) ORDER BY created_at ASC, id ASC',
                tuple(report_ids),
            )
            replies_by_bug = {}
            for reply in cursor.fetchall() or []:
                replies_by_bug.setdefault(reply['zgloszenie_id'], []).append(reply)

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
                report['odpowiedzi'] = replies_by_bug.get(report['id'], [])
    except Exception:
        flash('Nie udało się pobrać Twoich zgłoszeń.', 'error')
    finally:
        conn.close()

    return render_template('my_bug_reports.html', reports=reports, current_sort=sort_by)


@auth_bp.route('/moje_zgloszenia_bledow/odpowiedz/<int:bug_id>', methods=['POST'])
@login_required
def user_reply_bug_report(bug_id):
    login_value = (session.get('login') or '').strip()
    tresc = (request.form.get('odpowiedz_uzytkownika') or '').strip()
    if not tresc:
        flash('Treść wiadomości nie może być pusta.', 'error')
        return redirect(url_for('auth.my_bug_reports'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, login FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
        bug = cursor.fetchone()
        if not bug or bug['login'].lower() != login_value.lower():
            flash('Nie masz uprawnień do tego zgłoszenia.', 'error')
            return redirect(url_for('auth.my_bug_reports'))
        cursor.execute(
            'INSERT INTO zgloszenia_bledow_odpowiedzi '
            '(zgloszenie_id, autor_login, tresc, created_at) VALUES (%s, %s, %s, NOW())',
            (bug_id, login_value, tresc),
        )
        cursor.execute("UPDATE zgloszenia_bledow SET status = 'odpowiedz_uzytkownika' WHERE id = %s", (bug_id,))
        conn.commit()
        flash('Twoja odpowiedź została dodana do zgłoszenia.', 'success')
    except Exception as exc:
        conn.rollback()
        flash(f'Błąd dodawania odpowiedzi: {exc}', 'error')
    finally:
        conn.close()
    return redirect(url_for('auth.my_bug_reports'))


@auth_bp.route('/api/ack_bug_icon_intro', methods=['POST'])
@login_required
def ack_bug_icon_intro():
    session['show_bug_icon_intro'] = False
    return jsonify({'success': True})


@auth_bp.route('/api/zmien-moje-haslo', methods=['POST'])
@login_required
def zmien_moje_haslo():
    data = request.get_json(silent=True) or request.form
    stare_haslo = (data.get('stare_haslo') or '').strip()
    nowe_haslo = (data.get('nowe_haslo') or '').strip()
    powtorz_haslo = (data.get('powtorz_nowe_haslo') or data.get('powtorz_haslo') or '').strip()

    if not stare_haslo or not nowe_haslo:
        return jsonify({'success': False, 'message': 'Wypełnij wszystkie pola.'}), 400
    if nowe_haslo != powtorz_haslo:
        return jsonify({'success': False, 'message': 'Nowe hasła nie są identyczzne.'}), 400

    from app.services.password_policy_service import password_policy_service

    is_valid_pwd, pwd_error = password_policy_service.validate_password(nowe_haslo)
    if not is_valid_pwd:
        return jsonify({'success': False, 'message': pwd_error}), 400

    login_value = session.get('login')
    if not login_value:
        return jsonify({'success': False, 'message': 'Brak aktywnej sesji.'}), 401

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, haslo FROM uzytkownicy WHERE login = %s', (login_value,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'Nie znaleziono konta użytkownika.'}), 404
        if not check_password_hash(user['haslo'] or '', stare_haslo):
            return jsonify({'success': False, 'message': 'Aktualne hasło jest nieprawidłowe.'}), 400

        new_hash = generate_password_hash(nowe_haslo, method='pbkdf2:sha256')
        cursor.execute('UPDATE uzytkownicy SET haslo = %s WHERE id = %s', (new_hash, user['id']))
        conn.commit()

        from app.db import deactivate_all_user_sessions

        deactivate_all_user_sessions(
            user['id'],
            except_session_id=session.get('session_tracking_id'),
        )
        from app.core.audit import audit_log

        audit_log('Zmiana hasła', f'Użytkownik {login_value} zmienił własne hasło')
        return jsonify({'success': True, 'message': 'Hasło zostało pomyślnie zmienione.'})
    except Exception as exc:
        conn.rollback()
        current_app.logger.error('Błąd zmiany hasła dla %s: %s', login_value, exc)
        return jsonify({'success': False, 'message': 'Błąd serwera podczas zmiany hasła.'}), 500
    finally:
        conn.close()
