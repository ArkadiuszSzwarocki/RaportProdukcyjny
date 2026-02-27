from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from app.utils.validation import require_field
import logging
import json
import os
import sys
import zipfile
from datetime import date, datetime, timedelta, time
from io import BytesIO
from app.db import get_db_connection, rollover_unfinished, log_plan_history
from app.dto.paleta import PaletaDTO
from app.decorators import login_required, roles_required
from app.services.raport_service import RaportService
# Import test wrappers (used by admin UI test buttons)
try:
    from app.blueprints.routes_testing import test_generate_report as _test_generate_report
    from app.blueprints.routes_testing import test_download_zip as _test_download_zip
except Exception:
    _test_generate_report = None
    _test_download_zip = None

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

@api_bp.route('/edytuj_palete_ajax', methods=['POST'])
@login_required
def edytuj_palete_ajax():
    """Edytuj wagę palet w magazynie via AJAX"""
    try:
        data = request.get_json() or {}
        palete_id = data.get('id')
        nowa_waga = data.get('waga')
        data_planu = data.get('data_planu') or data.get('data_powrotu') or str(date.today())
        
        if not palete_id or nowa_waga is None:
            return jsonify({"success": False, "message": "Brakuje id lub wagi"}), 400
        
        nowa_waga = float(nowa_waga)
        if nowa_waga <= 0:
            return jsonify({"success": False, "message": "Waga musi być większa od 0"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz plan_id, sekcję i status palety
        cursor.execute("SELECT plan_id, sekcja, COALESCE(status,'') FROM palety_workowanie WHERE id=%s", (palete_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Paleta nie znaleziona"}), 404
        plan_id, sekcja, status = result

        # Jeśli paleta jest już przyjęta do magazynu, nie nadpisujemy oryginalnej kolumny `waga`.
        # Zamiast tego zapisujemy skorygowaną/ potwierdzoną wagę do `waga_potwierdzona`.
        if status == 'przyjeta':
            cursor.execute("UPDATE palety_workowanie SET waga_potwierdzona=%s WHERE id=%s", (nowa_waga, palete_id))
        else:
            # Aktualizuj wagę (Workowanie - do przyjęcia)
            cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (nowa_waga, palete_id))
            # Przelicz buffer (tonaz_rzeczywisty) dla Workowania
            if sekcja == 'Workowanie':
                cursor.execute(
                    "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
                    (plan_id, plan_id)
                )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Paleta edytowana"}), 200
    
    except Exception as e:
        logger = logging.getLogger('werkzeug')
        logger.error(f"Error in edytuj_palete_ajax: {str(e)}")
        return jsonify({"success": False, "message": f"Błąd: {str(e)}"}), 500


@api_bp.route('/usun_palete_ajax', methods=['POST'])
@login_required
def usun_palete_ajax():
    """Usuń paletę z magazynu via AJAX"""
    try:
        data = request.get_json() or {}
        palete_id = data.get('id')
        data_planu = data.get('data_planu') or data.get('data_powrotu') or str(date.today())
        
        if not palete_id:
            return jsonify({"success": False, "message": "Brakuje id palet"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz plan_id i sekcję palet
        cursor.execute("SELECT plan_id, sekcja FROM palety_workowanie WHERE id=%s", (palete_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Paleta nie znaleziona"}), 404
        
        plan_id, sekcja = result
        
        # Usuń paletę
        cursor.execute("DELETE FROM palety_workowanie WHERE id=%s", (palete_id,))
        
        # Przelicz buffer (tonaz_rzeczywisty) dla Workowania
        if sekcja == 'Workowanie':
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
                (plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Paleta usunięta"}), 200
    
    except Exception as e:
        logger = logging.getLogger('werkzeug')
        logger.error(f"Error in usun_palete_ajax: {str(e)}")
        return jsonify({"success": False, "message": f"Błąd: {str(e)}"}), 500


# ================= NOTATKI/WPISY NA DASHBOARD =================

@api_bp.route('/wpisy_na_date')
@login_required
def wpisy_na_date():
    """Pobierz wpisy dla wybranej daty i sekcji (AJAX)"""
    from app.utils.queries import QueryHelper
    
    try:
        data_str = request.args.get('data', str(date.today()))
        sekcja = request.args.get('sekcja', 'Zasyp')
        
        # Parse data
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Get wpisy
        wpisy = QueryHelper.get_dziennik_zmiany(data_obj, sekcja)
        
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

# Compatibility endpoints used by frontend admin test buttons
@api_bp.route('/test-generate-report')
def api_test_generate_report():
    if _test_generate_report is None:
        return jsonify({'success': False, 'message': 'Test generator unavailable'}), 503
    return _test_generate_report()


@api_bp.route('/test-download-zip')
def api_test_download_zip():
    if _test_download_zip is None:
        return jsonify({'success': False, 'message': 'Test ZIP unavailable'}), 503
    return _test_download_zip()


@api_bp.route('/shift_notes_na_date')
@login_required
def shift_notes_na_date():
    """Pobierz shift notes dla wybranej daty (AJAX)"""
    try:
        data_str = request.args.get('data', str(date.today()))
        
        # Parse data
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Get shift notes
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT id, note, author, created FROM shift_notes WHERE DATE(created) = %s ORDER BY created DESC"
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
        
        # Aktualizuj pole uszkodzone_worki
        cursor.execute(
            "UPDATE plan_produkcji SET uszkodzone_worki = %s WHERE id = %s AND sekcja = 'Workowanie'",
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
        cursor.execute(
            "SELECT id, produkt, tonaz, status, deleted_at FROM plan_produkcji WHERE DATE(data_planu) = %s AND is_deleted = 1 ORDER BY deleted_at DESC",
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

