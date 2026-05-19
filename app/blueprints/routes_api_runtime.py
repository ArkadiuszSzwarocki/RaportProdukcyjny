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
    @login_required
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

        return jsonify({'success': True, 'notifications': result, 'unread_count': len(result)})

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
                    'last_pallet': max(last_pallet_psd, last_pallet_agro) # Fallback
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