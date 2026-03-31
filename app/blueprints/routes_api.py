from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from app.utils.validation import require_field
import logging
import json
import os
import sys
import zipfile
import mysql.connector
from datetime import date, datetime, timedelta, time
from io import BytesIO
from app.db import get_db_connection, get_table_name, rollover_unfinished, log_plan_history, list_unread_notifications, mark_all_notifications_read, mark_notification_read, ensure_session_tracking_id, touch_active_session
from app.dto.paleta import PaletaDTO
from app.decorators import login_required, roles_required, dynamic_role_required
from app.services.raport_service import RaportService

api_bp = Blueprint('api', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data)

# ================= LANGUAGE SETTINGS =================

@api_bp.route('/set_language', methods=['GET', 'POST'])
@login_required
def set_language():
    """Zmień język interfejsu aplikacji"""
    try:
        from flask import make_response
        
        if request.method == 'GET':
            language = request.args.get('language', 'pl')
        else:
            data = request.get_json() or {}
            language = data.get('language', 'pl')
        
        # Walidacja języka
        if language not in ['pl', 'uk', 'en']:
            language = 'pl'
        
        session['app_language'] = language
        session.modified = True
        
        if request.method == 'GET':
            response = redirect(request.referrer or url_for('main.index'))
        else:
            response = jsonify({
                'success': True,
                'message': f'Język zmieniony na {language}',
                'language': language
            })
        # Ustaw cookie na 365 dni
        response.set_cookie('app_language', language, max_age=365*24*60*60, path='/')
        
        current_app.logger.info(f'Language changed to {language} for user {session.get("login")}')
        
        return response
    except Exception as e:
        current_app.logger.error(f'Error changing language: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 400

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
        from app.config import EMAIL_RECIPIENTS
        
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


# ================= MAGAZYN - AJAX ENDPOINTS =================


# ================= NOTATKI/WPISY NA DASHBOARD =================

@api_bp.route('/wpisy_na_date')
@login_required
def wpisy_na_date():
    """Pobierz wpisy dla wybranej daty i sekcji (AJAX)"""
    from app.utils.queries import QueryHelper
    
    try:
        data_str = request.args.get('data', str(date.today()))
        sekcja = request.args.get('sekcja', 'Zasyp')
        linia = request.args.get('linia', 'PSD')
        
        # Parse data
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Get wpisy
        wpisy = QueryHelper.get_dziennik_zmiany(data_obj, sekcja, linia=linia)
        
        # Format czas_start/czas_stop as HH:MM strings
        for w in wpisy:
            try:
                w[3] = w[3].strftime('%H:%M') if w[3] else ''
            except Exception:
                w[3] = str(w[3]) if w[3] else ''
            try:
                w[4] = w[4].strftime('%H:%M') if w[4] else ''
            except Exception:
                w[4] = str(w[4]) if w[4] else ''
        
        return jsonify({
            'success': True,
            'wpisy': wpisy,
            'data': data_str,
            'sekcja': sekcja
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@api_bp.route('/shift_notes_na_date')
@login_required
def shift_notes_na_date():
    """Pobierz shift notes dla wybranej daty (AJAX)"""
    try:
        data_str = request.args.get('data', str(date.today()))
        linia = request.args.get('linia', 'PSD')
        
        # Parse data
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Get shift notes
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        table_notes = get_table_name('shift_notes', linia)
        query = f"SELECT id, note, author, created FROM {table_notes} WHERE DATE(created) = %s ORDER BY created DESC"
        cursor.execute(query, (data_obj,))
        shift_notes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format notes
        formatted_notes = []
        for n in shift_notes:
            formatted_notes.append({
                'id': n['id'],
                'note': n['note'],
                'author': n['author'],
                'date': n['created'].strftime('%Y-%m-%d'),
                'time': n['created'].strftime('%H:%M:%S') if n['created'] else ''
            })
        
        return jsonify({
            'success': True,
            'notes': formatted_notes,
            'data': data_str
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400


@api_bp.route('/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Zwraca listę nieprzeczytanych powiadomień dla aktualnego użytkownika."""
    user_id = session.get('user_id')
    role = (session.get('rola') or '').lower()
    if not user_id or not role:
        return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

    try:
        limit = int(request.args.get('limit', 20))
        linia = request.args.get('linia', 'PSD')
    except Exception:
        limit = 20
        linia = 'PSD'

    notifications = list_unread_notifications(user_id, role, limit=limit, linia=linia)
    result = []
    for item in notifications:
        created_at = item.get('created_at')
        result.append({
            'id': item.get('id'),
            'type': item.get('typ'),
            'title': item.get('tytul'),
            'message': item.get('tresc'),
            'link_url': item.get('link_url'),
            'plan_id': item.get('plan_id'),
            'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else '',
            'recipient_role': item.get('odbiorca_rola'),
        })

    return jsonify({'success': True, 'notifications': result, 'unread_count': len(result)})


@api_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def read_notification(notification_id):
    """Oznacza pojedyncze powiadomienie jako przeczytane."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

    linia = request.args.get('linia', 'PSD')
    if not mark_notification_read(notification_id, user_id, linia=linia):
        return jsonify({'success': False, 'message': 'Nie udało się oznaczyć powiadomienia'}), 500

    return jsonify({'success': True})


@api_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def read_all_notifications():
    """Oznacza wszystkie powiadomienia dla roli użytkownika jako przeczytane."""
    user_id = session.get('user_id')
    role = (session.get('rola') or '').lower()
    if not user_id or not role:
        return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

    linia = request.args.get('linia', 'PSD')
    if not mark_all_notifications_read(user_id, role, linia=linia):
        return jsonify({'success': False, 'message': 'Nie udało się oznaczyć powiadomień'}), 500

    return jsonify({'success': True})


@api_bp.route('/session/ping', methods=['POST'])
@login_required
def session_ping():
    """Heartbeat endpoint used by the frontend to keep session presence fresh."""
    user_id = session.get('user_id')
    login = session.get('login')
    if not user_id or not login:
        return jsonify({'success': False, 'message': 'Brak danych użytkownika'}), 400

    session['session_tracking_id'] = ensure_session_tracking_id(session.get('session_tracking_id'))
    ok = touch_active_session(
        session_id=session.get('session_tracking_id'),
        user_id=user_id,
        login=login,
        role=session.get('rola'),
        pracownik_id=session.get('pracownik_id'),
        display_name=session.get('imie_nazwisko') or login,
        last_path=request.headers.get('X-Current-Path') or request.path,
    )
    if not ok:
        return jsonify({'success': False, 'message': 'Nie udało się odświeżyć sesji'}), 500

    return jsonify({'success': True})


@api_bp.route('/session/close', methods=['POST'])
@login_required
def session_close():
    """Close/deactivate current session (used by client-side unload/beacon).

    Marks the tracked session as inactive in DB and clears server session.
    Returns 204 No Content on success.
    """
    try:
        sid = session.get('session_tracking_id')
        try:
            from app.db import deactivate_active_session
            if sid:
                deactivate_active_session(sid)
        except Exception:
            pass
        # clear flask session server-side
        login = session.get('login', 'unknown')
        path_referred = request.headers.get('Referer', 'unknown')
        current_app.logger.critical(f"[SESSION_CLOSE] /api/session/close called by user {login} from {path_referred}")
        session.clear()
        return ('', 204)
    except Exception as e:
        current_app.logger.exception('Failed to close session: %s', e)
        return jsonify({'success': False, 'message': 'Nie udało się zamknąć sesji'}), 500


@api_bp.route('/update_uszkodzone_worki', methods=['POST'])
@login_required
def update_uszkodzone_worki():
    """Aktualizuj ilość uszkodzonych worków dla planu Workowania"""
    try:
        data = request.get_json()
        plan_id = data.get('plan_id')
        uszkodzone_worki = int(data.get('uszkodzone_worki', 0))
        
        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak plan_id'}), 400
        
        if uszkodzone_worki < 0:
            return jsonify({'success': False, 'message': 'Ilość nie może być ujemna'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        linia = data.get('linia', 'PSD')
        table_plan = get_table_name('plan_produkcji', linia)
        
        # Aktualizuj pole uszkodzone_worki
        cursor.execute(
            f"UPDATE {table_plan} SET uszkodzone_worki = %s WHERE id = %s AND sekcja = 'Workowanie'",
            (uszkodzone_worki, plan_id)
        )
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Plan nie znaleziony'}), 404
        
        # Loguj zmianę
        cursor.execute(
            "INSERT INTO plan_history (plan_id, action, changes, user_login, created_at) VALUES (%s, %s, %s, %s, NOW())",
            (plan_id, 'uszkodzone_worki_update', f'Uszkodzono: {uszkodzone_worki} worków', session.get('login'), )
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Zaktualizowano: {uszkodzone_worki} uszkodzonych worków',
            'uszkodzone_worki': uszkodzone_worki
        })
    except ValueError:
        return jsonify({'success': False, 'message': 'Nieprawidłowa liczba'}), 400
    except Exception as e:
        current_app.logger.exception(f'Error updating uszkodzone_worki: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/get_deleted_plans/<date>', methods=['GET'])
@roles_required('planista', 'admin')
def get_deleted_plans(date):
    """Pobierz usunięte (soft-deleted) zlecenia na dany dzień"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        linia = request.args.get('linia', 'PSD')
        table_plan = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT id, produkt, tonaz, status, deleted_at FROM {table_plan} WHERE DATE(data_planu) = %s AND is_deleted = 1 ORDER BY deleted_at DESC",
            (date,)
        )
        deleted_plans = cursor.fetchall()
        conn.close()
        
        result = []
        for row in deleted_plans:
            result.append({
                'id': row[0],
                'produkt': row[1],
                'tonaz': row[2],
                'status': row[3],
                'deleted_at': str(row[4]) if row[4] else None
            })
        
        return jsonify({'success': True, 'plans': result}), 200
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        current_app.logger.exception('Failed to get deleted plans for %s', date)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============ ATTENDANCE RECORD DELETION & RESTORATION ============

@api_bp.route('/obecnosc/delete-by-date', methods=['POST'])
@roles_required('admin')
def delete_obecnosc_by_date():
    """Delete all entries for a specific date and employee (admin only). Also removes from schedule. Saves deleted entries to session for undo."""
    try:
        data = request.get_json()
        date_str = data.get('date')
        pid = data.get('pid')
        
        if not date_str or not pid:
            return jsonify({'success': False, 'message': 'Brakuje parametrów'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz wszystkie wpisy na dany dzień dla tego pracownika
        cursor.execute(
            "SELECT id, pracownik_id, data_wpisu, typ, ilosc_godzin FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s",
            (pid, date_str)
        )
        deleted_entries = cursor.fetchall()
        
        # Pobierz też obsadę
        cursor.execute(
            "SELECT id, pracownik_id, data_wpisu, sekcja FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s",
            (pid, date_str)
        )
        deleted_obsada = cursor.fetchall()
        
        if not deleted_entries:
            conn.close()
            return jsonify({'success': False, 'message': 'Brak wpisów na podaną datę'}), 404
        
        # Usuń wszystkie wpisy z obecnosc
        cursor.execute("DELETE FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pid, date_str))
        
        # Usuń też z obsada_zmiany (aby osoba zniknęła z listy pracujących)
        cursor.execute("DELETE FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s", (pid, date_str))
        
        conn.commit()
        conn.close()
        
        # Zapisz do sesji dla możliwości undo (ostatni zestaw)
        session['deleted_obecnosc'] = {
            'date': date_str,
            'pid': pid,
            'entries': [
                {
                    'id': e['id'],
                    'pracownik_id': e['pracownik_id'],
                    'data_wpisu': str(e['data_wpisu']),
                    'typ': e['typ'],
                    'ilosc_godzin': e['ilosc_godzin']
                }
                for e in deleted_entries
            ],
            'obsada_entries': [
                {
                    'pracownik_id': o['pracownik_id'],
                    'data_wpisu': str(o['data_wpisu']),
                    'sekcja': o['sekcja']
                }
                for o in deleted_obsada
            ]
        }
        session.modified = True
        
        entry_types = ', '.join([e['typ'] for e in deleted_entries])
        current_app.logger.info(f"[ADMIN] Deleted {len(deleted_entries)} obecnosc entries AND {len(deleted_obsada)} obsada entries for date={date_str}, pid={pid}, types={entry_types}")
        
        return jsonify({
            'success': True, 
            'message': f"Usunięto {len(deleted_entries)} wpisów z dnia {date_str} ({entry_types}). Pracownik usunięty z listy obsady. Możesz cofnąć zmiany."
        })
    
    except Exception as e:
        current_app.logger.error(f"Error deleting obecnosc entries: {e}")
        return jsonify({'success': False, 'message': 'Błąd przy usuwaniu wpisów'}), 500


@api_bp.route('/obecnosc/<int:obecnosc_id>', methods=['DELETE'])
@roles_required('admin')
def delete_obecnosc(obecnosc_id):
    """Delete a single attendance entry by ID (admin only). Saves deleted entry to session for undo."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz wpis przed usunięciem (na wypadek undo)
        cursor.execute(
            "SELECT id, pracownik_id, data_wpisu, typ, ilosc_godzin FROM obecnosc WHERE id=%s",
            (obecnosc_id,)
        )
        deleted_entry = cursor.fetchone()
        
        if not deleted_entry:
            conn.close()
            return jsonify({'success': False, 'message': 'Wpis nie znaleziony'}), 404
        
        # Usuń wpis
        cursor.execute("DELETE FROM obecnosc WHERE id=%s", (obecnosc_id,))
        conn.commit()
        conn.close()
        
        # Zapisz do sesji dla możliwości undo
        session['deleted_obecnosc'] = {
            'id': deleted_entry['id'],
            'pracownik_id': deleted_entry['pracownik_id'],
            'data_wpisu': str(deleted_entry['data_wpisu']),
            'typ': deleted_entry['typ'],
            'ilosc_godzin': deleted_entry['ilosc_godzin']
        }
        session.modified = True
        
        current_app.logger.info(f"[ADMIN] Deleted obecnosc entry ID={obecnosc_id}, data={deleted_entry['data_wpisu']}, typ={deleted_entry['typ']}")
        
        return jsonify({'success': True, 'message': f"Usunięto wpis z dnia {deleted_entry['data_wpisu']} (typ: {deleted_entry['typ']}). Możesz cofnąć zmiany."})
    
    except Exception as e:
        current_app.logger.error(f"Error deleting obecnosc entry: {e}")
        return jsonify({'success': False, 'message': 'Błąd przy usuwaniu wpisu'}), 500


@api_bp.route('/obecnosc/restore', methods=['POST'])
@roles_required('admin')
def restore_ostatnia_usuniety():
    """Restore the last deleted attendance entry(ies) and schedule entries from session."""
    try:
        deleted = session.get('deleted_obecnosc')
        if not deleted:
            return jsonify({'success': False, 'message': 'Brak usuniętego wpisu do przywrócenia'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if it's a batch delete (multiple entries) or single
        if 'entries' in deleted:
            # Batch restore
            for entry in deleted['entries']:
                cursor.execute(
                    """INSERT INTO obecnosc (pracownik_id, data_wpisu, typ, ilosc_godzin) 
                       VALUES (%s, %s, %s, %s)""",
                    (entry['pracownik_id'], entry['data_wpisu'], entry['typ'], entry['ilosc_godzin'])
                )
            
            # Restore obsada entries too
            if 'obsada_entries' in deleted:
                for o in deleted['obsada_entries']:
                    cursor.execute(
                        """INSERT INTO obsada_zmiany (pracownik_id, data_wpisu, sekcja) 
                           VALUES (%s, %s, %s)""",
                        (o['pracownik_id'], o['data_wpisu'], o['sekcja'])
                    )
            
            conn.commit()
            count = len(deleted['entries'])
            date_str = deleted['date']
            msg = f"Przywrócono {count} wpisów z dnia {date_str}"
        else:
            # Single restore
            cursor.execute(
                """INSERT INTO obecnosc (pracownik_id, data_wpisu, typ, ilosc_godzin) 
                   VALUES (%s, %s, %s, %s)""",
                (deleted['pracownik_id'], deleted['data_wpisu'], deleted['typ'], deleted['ilosc_godzin'])
            )
            conn.commit()
            msg = f"Przywrócono wpis z dnia {deleted['data_wpisu']}"
        
        conn.close()
        
        # Wyczyść z sesji
        session.pop('deleted_obecnosc', None)
        session.modified = True
        
        current_app.logger.info(f"[ADMIN] Restored {count if 'entries' in deleted else 1} obecnosc entries and obsada")
        
        return jsonify({'success': True, 'message': msg})
    
    except Exception as e:
        current_app.logger.error(f"Error restoring obecnosc entry: {e}")
        return jsonify({'success': False, 'message': 'Błąd przy przywracaniu wpisu'}), 500


# ================= VALIDATION & ANOMALY DETECTION =================

@api_bp.route('/api/validate_plan_anomalies', methods=['POST'])
@login_required
@roles_required(['admin', 'lider'])
def validate_plan_anomalies():
    """
    Scan and fix plan anomalies (plans with tonaz_rzeczywisty > 0 but status='zaplanowane').
    Restricted to admin and lider roles.
    
    Returns JSON with scan results and count of fixed anomalies.
    """
    try:
        from app.services.planning_service import PlanningService
        
        success, message, fixed_count = PlanningService.validate_and_fix_anomalies()
        
        return jsonify({
            'success': success,
            'message': message,
            'fixed_count': fixed_count,
            'timestamp': datetime.now().isoformat()
        }), 200 if success else 400
        
    except Exception as e:
        current_app.logger.exception(f'Error in validate_plan_anomalies: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Błąd serwera: {str(e)}'
        }), 500


@api_bp.route('/api/plan/<int:plan_id>/check_status', methods=['GET'])
@login_required
def check_plan_status(plan_id):
    """
    Check if plan has status anomalies and return detailed info.
    Used for debugging and monitoring.
    
    Returns JSON with plan details and anomaly status.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        linia = request.args.get('linia', 'PSD')
        table_plan = get_table_name('plan_produkcji', linia)
        
        cursor.execute(f"""
            SELECT id, produkt, status, tonaz, tonaz_rzeczywisty, real_start, real_stop, sekcja
            FROM {table_plan}
            WHERE id=%s
        """, (plan_id,))
        
        plan = cursor.fetchone()
        conn.close()
        
        if not plan:
            return jsonify({
                'success': False,
                'message': f'Plan {plan_id} nie istnieje'
            }), 404
        
        # Detect anomaly
        tonaz_rz = plan['tonaz_rzeczywisty'] or 0
        has_anomaly = (tonaz_rz > 0 and plan['status'] == 'zaplanowane' and not plan['real_start'])
        
        return jsonify({
            'success': True,
            'plan_id': plan['id'],
            'produkt': plan['produkt'],
            'status': plan['status'],
            'tonaz_plan': plan['tonaz'],
            'tonaz_rzeczywisty': tonaz_rz,
            'real_start': plan['real_start'],
            'real_stop': plan['real_stop'],
            'sekcja': plan['sekcja'],
            'has_status_anomaly': has_anomaly,
            'anomaly_description': (
                'Plan has tonaz_rzeczywisty but status is zaplanowane (not yet started)' 
                if has_anomaly 
                else 'No anomalies detected'
            )
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Error checking plan status: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Błąd serwera: {str(e)}'
        }), 500

# ================= PRODUKTY / RECEPTURY =================

@api_bp.route('/produkty', methods=['GET'])
def get_produkty():
    """Zwraca listę dostępnych produktów (public - dla UI dropdownów)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, nazwa_produktu, nr_receptury, typ_produkcji
            FROM produkty_receptury
            ORDER BY nazwa_produktu ASC
        """)
        
        produkty = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'produkty': produkty
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Error fetching produkty: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Błąd serwera: {str(e)}'
        }), 500


@api_bp.route('/produkty', methods=['POST'])
@login_required
def add_produkt():
    """Dodaje nowy produkt do listy"""
    try:
        data = request.get_json() or {}
        nazwa = (data.get('nazwa_produktu') or '').strip()
        nr_receptury = (data.get('nr_receptury') or '').strip()
        typ_produkcji = (data.get('typ_produkcji') or 'worki_zgrzewane_25').strip()
        
        if not nazwa:
            return jsonify({
                'success': False,
                'message': 'Nazwa produktu jest wymagana'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO produkty_receptury (nazwa_produktu, nr_receptury, typ_produkcji)
                VALUES (%s, %s, %s)
            """, (nazwa, nr_receptury, typ_produkcji))
            
            conn.commit()
            product_id = cursor.lastrowid
            
            return jsonify({
                'success': True,
                'message': f'Produkt "{nazwa}" dodany do listy',
                'product_id': product_id
            }), 201
            
        except mysql.connector.errors.IntegrityError:
            return jsonify({
                'success': False,
                'message': f'Produkt "{nazwa}" już istnieje na liście'
            }), 409
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        current_app.logger.exception(f'Error adding produkt: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Błąd serwera: {str(e)}'
        }), 500


@api_bp.route('/produkty/<int:product_id>', methods=['PUT'])
@login_required
def update_produkt(product_id):
    """Aktualizuje produkt"""
    try:
        data = request.get_json() or {}
        nazwa = (data.get('nazwa_produktu') or '').strip()
        nr_receptury = (data.get('nr_receptury') or '').strip()
        typ_produkcji = (data.get('typ_produkcji') or 'worki_zgrzewane_25').strip()
        
        if not nazwa:
            return jsonify({
                'success': False,
                'message': 'Nazwa produktu jest wymagana'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE produkty_receptury
                SET nazwa_produktu=%s, nr_receptury=%s, typ_produkcji=%s
                WHERE id=%s
            """, (nazwa, nr_receptury, typ_produkcji, product_id))
            
            conn.commit()
            
            if cursor.rowcount == 0:
                return jsonify({
                    'success': False,
                    'message': 'Produkt nie znaleziony'
                }), 404
            
            return jsonify({
                'success': True,
                'message': f'Produkt "{nazwa}" zaktualizowany'
            }), 200
            
        except mysql.connector.errors.IntegrityError:
            return jsonify({
                'success': False,
                'message': f'Produkt "{nazwa}" już istnieje na liście'
            }), 409
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        current_app.logger.exception(f'Error updating produkt: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Błąd serwera: {str(e)}'
        }), 500


@api_bp.route('/produkty/<int:product_id>', methods=['DELETE'])
@login_required
def delete_produkt(product_id):
    """Usuwa produkt z listy"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sprawdź czy produkt jest używany w planach (we wszystkich liniach)
        table_plan_psd = get_table_name('plan_produkcji', 'PSD')
        table_plan_agro = get_table_name('plan_produkcji', 'Agro')
        
        cursor.execute(f"""
            SELECT (
                SELECT COUNT(*) FROM {table_plan_psd} 
                WHERE produkt = (SELECT nazwa_produktu FROM produkty_receptury WHERE id=%s)
            ) + (
                SELECT COUNT(*) FROM {table_plan_agro} 
                WHERE produkt = (SELECT nazwa_produktu FROM produkty_receptury WHERE id=%s)
            ) as total_count
        """, (product_id, product_id))
        
        result = cursor.fetchone()
        if result and result[0] > 0:
            return jsonify({
                'success': False,
                'message': 'Nie można usunąć produktu - jest używany w planach'
            }), 409
        
        cursor.execute("DELETE FROM produkty_receptury WHERE id=%s", (product_id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({
                'success': False,
                'message': 'Produkt nie znaleziony'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Produkt usunięty z listy'
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f'Error deleting produkt: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Błąd serwera: {str(e)}'
        }), 500
    finally:
        cursor.close()
        conn.close()