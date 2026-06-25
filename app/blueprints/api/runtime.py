import logging
from datetime import date, datetime

from flask import current_app, jsonify, redirect, request, session, url_for

from app.db import (
    ensure_session_tracking_id,
    get_db_connection,
    get_table_name,
    list_unread_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    touch_active_session,
)
from app.services.mqtt_service import get_latest_data
from app.decorators import login_required


def register_api_runtime_routes(api_bp):
    @api_bp.route('/log_frontend_error', methods=['POST'])
    def log_frontend_error():
        """Receive and log JavaScript errors from the frontend."""
        try:
            data = request.get_json() or {}
            error_msg = data.get('message', 'Unknown JS Error')
            stack = data.get('stack', '')
            url = data.get('url', '')
            user = session.get('login', 'unauthenticated')

            frontend_logger = logging.getLogger('frontend_errors')
            frontend_logger.error(f'JS ERROR: {error_msg} | URL: {url} | User: {user}\nStack: {stack}')
            return jsonify({'success': True}), 200
        except Exception as error:
            current_app.logger.error('Error in JS error trap: %s', error)
            return jsonify({'success': False}), 500

    @api_bp.route('/set_language', methods=['GET', 'POST'])
    def set_language():
        """Zmień język interfejsu aplikacji."""
        try:
            if request.method == 'GET':
                language = request.args.get('language', 'pl')
            else:
                data = request.get_json() or {}
                language = data.get('language', 'pl')

            if language not in ['pl', 'uk', 'en']:
                language = 'pl'

            session['app_language'] = language
            session.modified = True

            if request.method == 'GET':
                response = redirect(request.referrer or url_for('main.index'))
            else:
                response = jsonify({'success': True, 'message': f'Język zmieniony na {language}', 'language': language})

            response.set_cookie('app_language', language, max_age=365 * 24 * 60 * 60, path='/')
            current_app.logger.info('Language changed to %s for user %s', language, session.get('login'))
            return response
        except Exception as error:
            current_app.logger.error('Error changing language: %s', error)
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 400

    @api_bp.route('/email-config', methods=['GET'])
    @login_required
    def get_email_config():
        """Return configuration for report email recipients."""
        try:
            from app.config import EMAIL_RECIPIENTS

            return jsonify(
                {
                    'recipients': EMAIL_RECIPIENTS,
                    'subject_template': 'Raport produkcyjny z dnia {date}',
                    'configured': len(EMAIL_RECIPIENTS) > 0,
                    'count': len(EMAIL_RECIPIENTS),
                }
            ), 200
        except Exception as error:
            current_app.logger.error('[EMAIL-CONFIG] Błąd pobierania konfiguracji: %s', error)
            return jsonify({'error': 'Błąd pobierania konfiguracji', 'recipients': [], 'configured': False}), 500

    @api_bp.route('/wpisy_na_date')
    @login_required
    def wpisy_na_date():
        """Pobierz wpisy dla wybranej daty i sekcji (AJAX)."""
        from app.utils.queries import QueryHelper

        try:
            data_str = request.args.get('data', str(date.today()))
            sekcja = request.args.get('sekcja', 'Zasyp')
            linia = request.args.get('linia', 'PSD')
            data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
            wpisy = QueryHelper.get_dziennik_zmiany(data_obj, sekcja, linia=linia)

            for wpis in wpisy:
                try:
                    wpis[3] = wpis[3].strftime('%H:%M') if wpis[3] else ''
                except Exception:
                    wpis[3] = str(wpis[3]) if wpis[3] else ''
                try:
                    wpis[4] = wpis[4].strftime('%H:%M') if wpis[4] else ''
                except Exception:
                    wpis[4] = str(wpis[4]) if wpis[4] else ''

            return jsonify({'success': True, 'wpisy': wpisy, 'data': data_str, 'sekcja': sekcja})
        except Exception as error:
            return jsonify({'success': False, 'message': str(error)}), 400

    @api_bp.route('/shift_notes_na_date')
    @login_required
    def shift_notes_na_date():
        """Pobierz shift notes dla wybranej daty (AJAX)."""
        try:
            data_str = request.args.get('data', str(date.today()))
            linia = request.args.get('linia', 'PSD')
            data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            table_notes = get_table_name('shift_notes', linia)
            query = f'SELECT id, note, author, created FROM {table_notes} WHERE DATE(created) = %s ORDER BY created DESC'
            cursor.execute(query, (data_obj,))
            shift_notes = cursor.fetchall()
            cursor.close()
            conn.close()

            formatted_notes = []
            for note in shift_notes:
                formatted_notes.append(
                    {
                        'id': note['id'],
                        'note': note['note'],
                        'author': note['author'],
                        'date': note['created'].strftime('%Y-%m-%d'),
                        'time': note['created'].strftime('%H:%M:%S') if note['created'] else '',
                    }
                )

            return jsonify({'success': True, 'notes': formatted_notes, 'data': data_str})
        except Exception as error:
            return jsonify({'success': False, 'message': str(error)}), 400

    @api_bp.route('/notifications', methods=['GET'])
    @login_required
    def get_notifications():
        """Zwraca listę nieprzeczytanych powiadomień dla aktualnego użytkownika."""
        user_id = session.get('user_id')
        role = (session.get('rola') or '').lower()
        login = session.get('login')
        if not user_id or not role:
            return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

        try:
            limit = int(request.args.get('limit', 20))
            linia = request.args.get('linia', 'PSD')
        except Exception:
            limit = 20
            linia = 'PSD'

        notifications = list_unread_notifications(user_id, role, login=login, limit=limit, linia=linia)
        result = []
        for item in notifications:
            created_at = item.get('created_at')
            result.append(
                {
                    'id': item.get('id'),
                    'type': item.get('typ'),
                    'title': item.get('tytul'),
                    'message': item.get('tresc'),
                    'link_url': item.get('link_url'),
                    'plan_id': item.get('plan_id'),
                    'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else '',
                    'recipient_role': item.get('odbiorca_rola'),
                }
            )

        # Sprawdzenie równoległych logowań
        concurrent_alert = False
        from app.db import get_all_active_sessions_for_user
        import time
        current_sid = session.get('session_tracking_id')
        active_sessions = get_all_active_sessions_for_user(user_id)
        if len(active_sessions) > 1:
            latest_session = active_sessions[-1]
            if latest_session.get('session_id') != current_sid:
                latest_ts = latest_session.get('logged_in_at').timestamp() if latest_session.get('logged_in_at') else 0
                accepted_ts = session.get('accepted_concurrent_ts', 0)
                # Tylko powiadamiamy jeśli nowa sesja pojawiła się po naszym logowaniu/zaakceptowaniu
                # i unikamy ostrzeżeń o zamierzchłych sesjach (< 1 dzień).
                if latest_ts > accepted_ts and (time.time() - latest_ts) < 86400:
                    concurrent_alert = True

        return jsonify({
            'success': True, 
            'notifications': result, 
            'unread_count': len(result),
            'concurrent_alert': concurrent_alert
        })

    @api_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
    @login_required
    def read_notification(notification_id):
        """Oznacza pojedyncze powiadomienie jako przeczytane."""
        user_id = session.get('user_id')
        role = (session.get('rola') or '').lower()
        login = session.get('login')
        if not user_id or not role:
            return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

        linia = request.args.get('linia', 'PSD')
        if not mark_notification_read(notification_id, user_id, role=role, login=login, linia=linia):
            return jsonify({'success': False, 'message': 'Nie udało się oznaczyć powiadomienia'}), 500

        return jsonify({'success': True})

    @api_bp.route('/notifications/read-all', methods=['POST'])
    @login_required
    def read_all_notifications():
        """Oznacza wszystkie powiadomienia dla roli użytkownika jako przeczytane."""
        user_id = session.get('user_id')
        role = (session.get('rola') or '').lower()
        login = session.get('login')
        if not user_id or not role:
            return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

        linia = request.args.get('linia', 'PSD')
        if not mark_all_notifications_read(user_id, role, login=login, linia=linia):
            return jsonify({'success': False, 'message': 'Nie udało się oznaczyć powiadomień'}), 500

        return jsonify({'success': True})

    @api_bp.route('/notify-planner', methods=['POST'])
    @login_required
    def notify_planner():
        """Służy operatorowi do powiadomienia planisty o braku zleceń."""
        try:
            data = request.get_json() or {}
            sekcja = data.get('sekcja', 'Produkcja')
            linia = data.get('linia', 'PSD')
            
            user_login = session.get('login', 'Operator')
            
            from app.db import create_notifications
            
            # Tworzymy powiadomienie dla ról: planista i admin
            tytul = f"Brak zleceń: {sekcja} ({linia})"
            tresc = f"Operator {user_login} zgłasza brak zaplanowanych zleceń w sekcji {sekcja} na linii {linia}. Proszę o weryfikację planu."
            
            create_notifications(
                typ='brak_zlecen',
                tytul=tytul,
                tresc=tresc,
                recipient_roles=['planista', 'admin', 'masteradmin'],
                link_url=url_for('planista.panel_planisty', linia=linia),
                created_by_user_id=session.get('user_id')
            )
            
            return jsonify({'success': True, 'message': 'Powiadomienie zostało wysłane do planisty.'})
        except Exception as error:
            current_app.logger.error('Error sending notification to planner: %s', error)
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 400

    @api_bp.route('/system_state', methods=['GET'])
    @login_required
    def get_system_state():
        """Returns the latest sequence IDs for various system entities to enable smart polling."""
        try:
            linia = request.args.get('linia', 'PSD').upper()
            
            import time
            global _system_state_cache
            if '_system_state_cache' not in globals():
                _system_state_cache = {}

            now = time.time()
            cached = _system_state_cache.get(linia)
            if cached and (now - cached['timestamp'] < 2.0):
                return jsonify(cached['data'])

            from app.db import get_table_name, get_db_connection

            # Resolve table names based on line
            table_ruch = get_table_name('magazyn_ruch', linia)
            table_plans = get_table_name('plan_produkcji', linia)

            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. Last warehouse movement ID
            cursor.execute(f"SELECT MAX(id) FROM {table_ruch}")
            last_move = cursor.fetchone()[0] or 0

            # 2. Last production plan entry ID
            cursor.execute(f"SELECT MAX(id) FROM {table_plans}")
            last_plan = cursor.fetchone()[0] or 0

            # 3. Last notification ID
            cursor.execute("SELECT MAX(id) FROM powiadomienia")
            last_notif = cursor.fetchone()[0] or 0

            # 4. Last change in user assignments (stanowiska) for AGRO
            last_station_change = 0
            if linia == 'AGRO':
                cursor.execute("SELECT MAX(UNIX_TIMESTAMP(updated_at)) FROM agro_stanowiska")
                last_station_change = cursor.fetchone()[0] or 0
                
            # Fetch last pallets for BOTH halls to be sure
            cursor.execute(f"SELECT MAX(id) FROM {get_table_name('palety_workowanie', 'PSD')}")
            last_pallet_psd = cursor.fetchone()[0] or 0
            cursor.execute(f"SELECT MAX(id) FROM {get_table_name('palety_workowanie', 'AGRO')}")
            last_pallet_agro = cursor.fetchone()[0] or 0

            # 5. Fetch last zasyp (szarża) for BOTH halls
            try:
                cursor.execute(f"SELECT MAX(id) FROM {get_table_name('szarze', 'PSD')}")
                last_zasyp_psd = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT MAX(id) FROM {get_table_name('szarze', 'AGRO')}")
                last_zasyp_agro = cursor.fetchone()[0] or 0
            except Exception:
                last_zasyp_psd = 0
                last_zasyp_agro = 0

            # 6. Fetch last failure (awaria) ID
            try:
                cursor.execute("SELECT MAX(id) FROM dziennik_zmiany")
                last_awaria = cursor.fetchone()[0] or 0
            except Exception:
                last_awaria = 0

            # 7. Fetch last dosypka ID for BOTH halls
            try:
                cursor.execute(f"SELECT MAX(id) FROM {get_table_name('dosypki', 'PSD')}")
                last_dosypka_psd = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT MAX(id) FROM {get_table_name('dosypki', 'AGRO')}")
                last_dosypka_agro = cursor.fetchone()[0] or 0
            except Exception:
                last_dosypka_psd = 0
                last_dosypka_agro = 0

            # 8. Fetch state sum of dosypki (potwierdzone + anulowana) to detect confirmations/cancellations
            try:
                cursor.execute(f"SELECT COALESCE(SUM(potwierdzone + COALESCE(anulowana, 0)), 0) FROM {get_table_name('dosypki', 'PSD')}")
                state_dosypka_psd = int(cursor.fetchone()[0] or 0)
                cursor.execute(f"SELECT COALESCE(SUM(potwierdzone + COALESCE(anulowana, 0)), 0) FROM {get_table_name('dosypki', 'AGRO')}")
                state_dosypka_agro = int(cursor.fetchone()[0] or 0)
            except Exception:
                state_dosypka_psd = 0
                state_dosypka_agro = 0

            cursor.close()
            conn.close()

            response_data = {
                'success': True,
                'state': {
                    'last_move': last_move,
                    'last_plan': last_plan,
                    'last_notif': last_notif,
                    'last_station_change': last_station_change,
                    'last_pallet_psd': last_pallet_psd,
                    'last_pallet_agro': last_pallet_agro,
                    'last_pallet': max(last_pallet_psd, last_pallet_agro),
                    'last_zasyp_psd': last_zasyp_psd,
                    'last_zasyp_agro': last_zasyp_agro,
                    'last_awaria': last_awaria,
                    'last_dosypka_psd': last_dosypka_psd,
                    'last_dosypka_agro': last_dosypka_agro,
                    'state_dosypka': state_dosypka_psd + state_dosypka_agro
                }
            }
            
            _system_state_cache[linia] = {
                'timestamp': now,
                'data': response_data
            }
            return jsonify(response_data)
        except Exception as e:
            current_app.logger.error(f"Error in get_system_state: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @api_bp.route('/session/ping', methods=['POST'])
    @login_required
    def session_ping():
        """Heartbeat endpoint used by the frontend to keep session presence fresh."""
        user_id = session.get('user_id')
        login = session.get('login')
        if not user_id or not login:
            return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

        session['session_tracking_id'] = ensure_session_tracking_id(session.get('session_tracking_id'))
        forwarded_for = request.headers.get('X-Forwarded-For', '')
        client_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr)
        ok = touch_active_session(
            session_id=session.get('session_tracking_id'),
            user_id=user_id,
            login=login,
            role=session.get('rola'),
            pracownik_id=session.get('pracownik_id'),
            display_name=session.get('imie_nazwisko') or login,
            last_path=request.headers.get('X-Current-Path') or request.path,
            ip_address=client_ip,
        )
        if not ok:
            return jsonify({'success': False, 'message': 'Nie udało się odświeżyć sesji'}), 500

        return jsonify({'success': True})

    @api_bp.route('/session/accept-concurrent', methods=['POST'])
    @login_required
    def session_accept_concurrent():
        """Accepts concurrent logins by saving the timestamp to the session."""
        import time
        session['accepted_concurrent_ts'] = time.time()
        return jsonify({'success': True})

    @api_bp.route('/session/reject-concurrent', methods=['POST'])
    @login_required
    def session_reject_concurrent():
        """Rejects concurrent logins by deactivating all other sessions for this user."""
        user_id = session.get('user_id')
        current_sid = session.get('session_tracking_id')
        if not user_id or not current_sid:
            return jsonify({'success': False, 'message': 'Brak danych sesji'}), 400
            
        from app.db import deactivate_other_user_sessions
        ok = deactivate_other_user_sessions(user_id, current_sid)
        if ok:
            import time
            session['accepted_concurrent_ts'] = time.time()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Błąd bazy danych'}), 500

    @api_bp.route('/session/close', methods=['POST'])
    @login_required
    def session_close():
        """Close/deactivate current session (used by client-side unload/beacon)."""
        try:
            sid = session.get('session_tracking_id')
            try:
                from app.db import deactivate_active_session

                if sid:
                    deactivate_active_session(sid)
            except Exception:
                pass

            login = session.get('login', 'unknown')
            path_referred = request.headers.get('Referer', 'unknown')
            current_app.logger.critical('[SESSION_CLOSE] /api/session/close called by user %s from %s', login, path_referred)
            session.clear()
            return ('', 204)
        except Exception as error:
            current_app.logger.exception('Failed to close session: %s', error)
            return jsonify({'success': False, 'message': 'Nie udało się zamknąć sesji'}), 500

    # ===========================================================
    # WEB PUSH NOTIFICATION ENDPOINTS
    # ===========================================================

    @api_bp.route('/push/vapid-public-key', methods=['GET'])
    def push_vapid_public_key():
        """Zwraca publiczny klucz VAPID potrzebny przeglądarce do subskrypcji push."""
        try:
            from app.config import VAPID_PUBLIC_KEY
            if not VAPID_PUBLIC_KEY:
                return jsonify({'success': False, 'message': 'VAPID not configured'}), 503
            return jsonify({'success': True, 'publicKey': VAPID_PUBLIC_KEY})
        except Exception as error:
            current_app.logger.error('[PUSH] Error getting VAPID public key: %s', error)
            return jsonify({'success': False}), 500

    @api_bp.route('/push/subscribe', methods=['POST'])
    @login_required
    def push_subscribe():
        """Zapisuje subskrypcję Web Push dla zalogowanego użytkownika."""
        user_id = session.get('user_id')
        login = session.get('login')
        rola = (session.get('rola') or '').lower()

        if not user_id or not login:
            return jsonify({'success': False, 'message': 'Brak danych sesji'}), 400

        try:
            data = request.get_json() or {}
            endpoint = data.get('endpoint', '').strip()
            keys = data.get('keys', {})
            p256dh = keys.get('p256dh', '').strip()
            auth = keys.get('auth', '').strip()

            if not endpoint or not p256dh or not auth:
                return jsonify({'success': False, 'message': 'Niekompletne dane subskrypcji'}), 400

            from app.db import save_push_subscription
            ok = save_push_subscription(user_id, login, rola, endpoint, p256dh, auth)

            if ok:
                current_app.logger.info('[PUSH] Subscription saved for user %s (role: %s)', login, rola)
                return jsonify({'success': True, 'message': 'Subskrypcja push zapisana.'})
            else:
                return jsonify({'success': False, 'message': 'Błąd zapisu subskrypcji'}), 500
        except Exception as error:
            current_app.logger.exception('[PUSH] Error saving subscription: %s', error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/push/unsubscribe', methods=['POST'])
    @login_required
    def push_unsubscribe():
        """Usuwa subskrypcję Web Push dla zalogowanego użytkownika."""
        try:
            data = request.get_json() or {}
            endpoint = data.get('endpoint', '').strip()
            if not endpoint:
                return jsonify({'success': False, 'message': 'Brak endpointu'}), 400

            from app.db import delete_push_subscription
            ok = delete_push_subscription(endpoint)
            login = session.get('login', 'unknown')
            current_app.logger.info('[PUSH] Subscription removed for user %s', login)
            return jsonify({'success': ok})
        except Exception as error:
            current_app.logger.exception('[PUSH] Error removing subscription: %s', error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/mqtt_simulate', methods=['POST'])
    @login_required
    def mqtt_simulate():
        """Dodaje sztuczne wartości do liczników MQTT w celu testowania (w tym rozliczenia folii)."""
        # Dostępne tylko dla masteradmin / admin / testów
        rola = (session.get('rola') or '').lower().replace(' ', '').replace('_', '')
        if rola not in ['masteradmin', 'admin', 'planista', 'lider', 'magazynier', 'pracownik']:
            return jsonify({'success': False, 'message': 'Brak uprawnień'}), 403

        try:
            data = request.get_json() or {}
            add_counter = int(data.get('add_counter', 0))
            add_pallets = int(data.get('add_pallets', 0))
            
            from app.services.mqtt_service import simulate_machine_data, get_latest_data
            from app.db import get_db_connection
            
            latest = get_latest_data()
            current = latest.get('counter', 0)
            
            # Jeśli serwer został zrestartowany, licznik in-memory to 0. Musimy go najpierw "podciągnąć" 
            # pod licznik_start aktywnych rolek, żeby przyrost był widoczny.
            if current < 10:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT MAX(start_machine_counter) FROM plan_produkcji_agro WHERE status='W TOKU'")
                    max_plan_start = cursor.fetchone()[0] or 0
                    
                    cursor.execute("SELECT MAX(licznik_start) FROM agro_plan_opakowania WHERE is_active = TRUE")
                    max_rolka_start = cursor.fetchone()[0] or 0
                    
                    max_start = max(max_plan_start, max_rolka_start)
                    if max_start and current < max_start:
                        current = max_start
                        simulate_machine_data(add_counter=(max_start - latest.get('counter', 0)))
                except Exception:
                    pass
                finally:
                    conn.close()

            simulate_machine_data(add_counter=add_counter, add_pallets=add_pallets)
            
            latest = get_latest_data()
            current_app.logger.info(
                f"[MQTT-SIM] Użytkownik {session.get('login')} dodał {add_counter} worków. "
                f"Nowy stan: counter={latest.get('counter')}, pallet={latest.get('pallet_counter')}"
            )
            return jsonify({
                'success': True, 
                'message': f'Zasymulowano produkcję: dodano {add_counter} worków.',
                'new_state': {
                    'counter': latest.get('counter'),
                    'pallet_counter': latest.get('pallet_counter')
                }
            })
        except Exception as error:
            current_app.logger.error('[MQTT-SIM] Error: %s', error)
            return jsonify({'success': False, 'message': str(error)}), 400