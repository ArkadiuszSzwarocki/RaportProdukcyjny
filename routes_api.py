from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from utils.validation import require_field
import logging
import json
import os
import sys
import zipfile
from datetime import date, datetime, timedelta, time
from io import BytesIO
from db import get_db_connection, rollover_unfinished, log_plan_history
from dto.paleta import PaletaDTO
from decorators import login_required, roles_required
from services.raport_service import RaportService

api_bp = Blueprint('api', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('index', sekcja=sekcja, data=data)

# ================= LANGUAGE SETTINGS =================

@api_bp.route('/set_language', methods=['POST'])
@login_required
def set_language():
    """Zmień język interfejsu aplikacji"""
    try:
        from flask import make_response
        
        data = request.get_json()
        language = data.get('language', 'pl')
        
        # Walidacja języka
        if language not in ['pl', 'uk', 'en']:
            language = 'pl'
        
        session['app_language'] = language
        session.modified = True
        
        # Odpowiedź z cookie
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

# ================= OBSADA I INNE =================
@api_bp.route('/dodaj_obecnosc', methods=['POST'])
@login_required
def dodaj_obecnosc():
    conn = get_db_connection()
    cursor = conn.cursor()
    typ = request.form.get('typ')
    pracownik_id = request.form.get('pracownik_id')
    godziny = request.form.get('godziny', 0)
    try:
        godziny_val = float(str(godziny).replace(',', '.'))
    except Exception:
        godziny_val = 0.0
    komentarz = request.form.get('komentarz', '')
    # Server-side: walidacja wymaganych pól i czytelny komunikat
    missing = []
    if not pracownik_id:
        missing.append('Pracownik')
    if not typ:
        missing.append('Typ')
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        if not od: missing.append('Czas (od)')
        if not do: missing.append('Czas (do)')
    if missing:
        try:
            flash('Brakuje wymaganych pól: ' + ', '.join(missing), 'warning')
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return redirect(bezpieczny_powrot())
    # Jeśli Wyjscie prywatne — wymagamy podania zakresu czasu
    od = None
    do = None
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        # Dołączamy zakres czasowy do komentarza dla zapisu (kompatybilność wsteczna)
        komentarz = f"Wyjście prywatne od {od} do {do}" + (f" — {komentarz}" if komentarz else '')

    # Zapisz też osobne kolumny wyjscie_od/wyjscie_do (mogą być NULL jeśli nie dotyczy)
    cursor.execute(
        "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz, wyjscie_od, wyjscie_do) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (date.today(), pracownik_id, typ, godziny_val, komentarz, od, do)
    )
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())


@api_bp.route('/edytuj_godziny', methods=['POST'])
@login_required
def edytuj_godziny():
    """Edytuj/liczba godzin dla danego pracownika i daty (AJAX)."""
    try:
        pracownik_id = request.form.get('pracownik_id') or request.args.get('pracownik_id')
        date_str = request.form.get('date') or request.args.get('date')
        from utils.validation import require_field
        godziny = require_field(request.form, 'godziny')
        if not pracownik_id or not date_str:
            return jsonify({'success': False, 'message': 'Brak parametrów'}), 400
        try:
            pid = int(pracownik_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowy pracownik'}), 400

        # Uprawnienia: właściciel może edytować swoje godziny, lider/admin może edytować inne
        try:
            my_pid = session.get('pracownik_id')
            my_role = (session.get('rola') or '').lower()
        except Exception:
            my_pid = None; my_role = ''
        if my_pid != pid and my_role not in ('lider', 'admin'):
            return jsonify({'success': False, 'message': 'Brak uprawnień'}), 403

        try:
            hours_val = float(str(godziny).replace(',', '.'))
        except Exception:
            hours_val = 0.0

        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy istnieje wiersz obecnosc dla tej daty i pracownika
        cursor.execute("SELECT id FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s LIMIT 1", (pid, date_str))
        res = cursor.fetchone()
        if res:
            cursor.execute("UPDATE obecnosc SET ilosc_godzin=%s WHERE id=%s", (hours_val, res[0]))
        else:
            cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (date_str, pid, 'Obecność', hours_val, 'Edytowano ręcznie'))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Godziny zapisane'})
    except Exception:
        current_app.logger.exception('Error editing hours')
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500


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
        from config import EMAIL_RECIPIENTS
        
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


# ================= WZNOWIENIE ZLECEŃ Z POPRZEDNIEGO DNIA =================

@api_bp.route('/wznow_zlecenia_z_wczoraj', methods=['POST'])
@login_required
def wznow_zlecenia_z_wczoraj():
    """
    Endpoint wznawia wszystkie zlecenia ze statusem 'wstrzymane' 
    z poprzedniego dnia (zmieniam status na 'w toku').
    """
    try:
        print(f"[WZNOW-WCZORAJ] Starting auto-resume handler")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-WCZORAJ] Querying for plans from {wczoraj_str}")
        
        # Wznów wszystkie zlecenia w statusie 'wstrzymane' z poprzedniego dnia
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str,))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-WCZORAJ] OK Success: Resumed {resumed_count} plans from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "message": f"Wznowiono {resumed_count} zleceń z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-WCZORAJ] ERROR Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Błąd przy wznowienia zleceń z poprzedniego dnia"
        }), 500


# ================= RĘCZNE WZNOWIENIE ZLECEŃ DLA SEKCJI =================

@api_bp.route('/wznow_zlecenia_sekcji/<sekcja>', methods=['POST'])
@login_required
def wznow_zlecenia_sekcji(sekcja):
    """
    Endpoint ręcznego wznowienia wszystkich zleceń 'wstrzymane' 
    z poprzedniego dnia dla wybranej sekcji.
    """
    try:
        print(f"[WZNOW-SEKCJA] Starting handler for sekcja={sekcja}")
        
        # Walidacja sekcji
        if sekcja not in ['Zasyp', 'Workowanie', 'Pakowanie', 'Magazyn']:
            print(f"[WZNOW-SEKCJA] ✗ Invalid sekcja: {sekcja}")
            return jsonify({
                "success": False,
                "error": f"Nieznana sekcja: {sekcja}",
                "message": "Sekcja musi być jedną z: Zasyp, Workowanie, Pakowanie, Magazyn"
            }), 400
        
        print(f"[WZNOW-SEKCJA] Sekcja valid: {sekcja}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-SEKCJA] Querying plans from {wczoraj_str} for sekcja={sekcja}")
        
        # Wznów wszystkie zlecenia 'wstrzymane' z poprzedniego dnia dla tej sekcji
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND sekcja = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str, sekcja))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-SEKCJA] ✓ Success: Resumed {resumed_count} plans for sekcja={sekcja} from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "sekcja": sekcja,
            "message": f"✅ Wznowiono {resumed_count} zleceń dla {sekcja} z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-SEKCJA] ✗ Error for sekcja={sekcja}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Błąd przy wznowienia zleceń dla {sekcja}"
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
        data_powrotu = data.get('data_powrotu') or str(date.today())
        
        if not palete_id or nowa_waga is None:
            return jsonify({"success": False, "message": "Brakuje id lub wagi"}), 400
        
        nowa_waga = float(nowa_waga)
        if nowa_waga <= 0:
            return jsonify({"success": False, "message": "Waga musi być większa od 0"}), 400
        
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
        
        # Aktualizuj wagę
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
        data_powrotu = data.get('data_powrotu') or str(date.today())
        
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


# ================= TEST ENDPOINTS FOR DOWNLOAD =================

@api_bp.route('/test-download-page')
@login_required
def test_download_page():
    """Strona testowa do pobrania raportów"""
    return render_template('test_download.html')


@api_bp.route('/test-generate-report')
@login_required
def test_generate_report():
    """Test endpoint - Wygeneruj raport bez pobierania"""
    try:
        data_str = request.args.get('data') or str(date.today())
        
        print(f"\n[TEST-GENERATE] Starting report generation for {data_str}")
        sys.stdout.flush()
        
        # Import generator
        from generator_raportow import generuj_paczke_raportow
        
        # Generate reports
        xls_path, txt_path, pdf_path = generuj_paczke_raportow(data_str, "Test raport", "Admin")
        
        # Check if files exist
        xls_exists = os.path.exists(xls_path) if xls_path else False
        txt_exists = os.path.exists(txt_path) if txt_path else False
        pdf_exists = os.path.exists(pdf_path) if pdf_path else False
        
        print(f"[TEST-GENERATE] XLS: {xls_path} (exists={xls_exists})")
        print(f"[TEST-GENERATE] TXT: {txt_path} (exists={txt_exists})")
        print(f"[TEST-GENERATE] PDF: {pdf_path} (exists={pdf_exists})")
        sys.stdout.flush()
        
        return jsonify({
            "success": True,
            "message": f"OK Raport wygenerowany dla {data_str}",
            "xls": xls_path,
            "xls_exists": xls_exists,
            "txt": txt_path,
            "txt_exists": txt_exists,
            "pdf": pdf_path,
            "pdf_exists": pdf_exists
        }), 200
        
    except Exception as e:
        print(f"[TEST-GENERATE] ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"ERROR Blad: {str(e)}"
        }), 500


@api_bp.route('/test-download-zip')
@login_required
def test_download_zip():
    """Test endpoint - Zwróć prosty ZIP do pobrania"""
    try:
        data_str = request.args.get('data') or str(date.today())
        
        print(f"\n[TEST-ZIP] Starting ZIP creation for {data_str}")
        sys.stdout.flush()
        
        # Create test ZIP with dummy file
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add test file
            test_content = f"Test raport dla daty: {data_str}\nGodzina: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            zip_file.writestr("test_raport.txt", test_content)
            
            # Try to add real reports if they exist
            raporty_dir = 'raporty'
            if os.path.exists(raporty_dir):
                for file in os.listdir(raporty_dir):
                    if data_str in file and file.endswith(('.xlsx', '.txt', '.pdf')):
                        file_path = os.path.join(raporty_dir, file)
                        zip_file.write(file_path, arcname=file)
                        print(f"[TEST-ZIP] Added: {file}")
                        sys.stdout.flush()
        
        zip_buffer.seek(0)
        
        print(f"[TEST-ZIP] ZIP created, size: {len(zip_buffer.getvalue())} bytes")
        sys.stdout.flush()
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"Test_Raporty_{data_str}.zip"
        )
        
    except Exception as e:
        print(f"[TEST-ZIP] ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"ERROR Blad: {str(e)}"
        }), 500

# ================= NOTATKI/WPISY NA DASHBOARD =================

@api_bp.route('/wpisy_na_date')
@login_required
def wpisy_na_date():
    """Pobierz wpisy dla wybranej daty i sekcji (AJAX)"""
    from utils.queries import QueryHelper
    
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