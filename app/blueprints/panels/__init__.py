from flask import Blueprint, render_template, request, redirect, session, current_app, send_file, url_for, jsonify
from datetime import date, datetime, timedelta
from collections import defaultdict
import json
import os

from app.db import get_db_connection
from app.decorators import login_required, roles_required, zarzad_required, dynamic_role_required
from .hours_data import build_employee_summary, build_hours_calendar
from app.services.attendance_service import AttendanceService
from app.services.overtime_service import OvertimeService

# Import QueryHelper if available for complex queries
try:
    from app.utils.queries import QueryHelper
except ImportError:
    QueryHelper = None

panels_bp = Blueprint('panels', __name__)


@panels_bp.route('/panel_wnioski_page', methods=['GET'])
@login_required
def panel_wnioski_page():
    """Panel widok wniosków o wolne - dla liderów/adminów pokazuje wszystkie pending, dla pracowników - swoje."""
    wnioski = []
    approved_wnioski = []
    conn = None
    try:
        # Use AttendanceService instead of QueryHelper for consistency
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        rola = session.get('rola', '')
        
        if rola in ['admin', 'lider', 'masteradmin']:
            # Admin and lider see all pending requests
            cursor.execute("""
                SELECT lr.*, p.imie_nazwisko AS pracownik 
                FROM wnioski_wolne lr 
                JOIN pracownicy p ON lr.pracownik_id = p.id 
                WHERE lr.status = 'pending' 
                ORDER BY lr.data_od DESC
            """)
            wnioski = cursor.fetchall()
            
            # Also show recently approved/rejected for context
            cursor.execute("""
                SELECT lr.*, p.imie_nazwisko AS pracownik 
                FROM wnioski_wolne lr 
                JOIN pracownicy p ON lr.pracownik_id = p.id 
                WHERE lr.status IN ('approved', 'rejected') 
                AND lr.data_od >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                ORDER BY lr.data_od DESC
                LIMIT 20
            """)
            approved_wnioski = cursor.fetchall()
        else:
            # Regular employees see only their own requests
            user_id = session.get('user_id')
            if user_id:
                cursor.execute("""
                    SELECT lr.*, p.imie_nazwisko AS pracownik 
                    FROM wnioski_wolne lr 
                    JOIN pracownicy p ON lr.pracownik_id = p.id 
                    WHERE lr.pracownik_id = %s 
                    ORDER BY lr.data_od DESC
                """, (user_id,))
                all_wnioski = cursor.fetchall()
                
                # Separate pending from others
                wnioski = [w for w in all_wnioski if w['status'] == 'pending']
                approved_wnioski = [w for w in all_wnioski if w['status'] in ('approved', 'rejected')]
        
        return render_template('panels/wnioski_panel.html', wnioski=wnioski, approved_wnioski=approved_wnioski)
        
    except Exception as e:
        current_app.logger.error(f"Error loading panel_wnioski_page: {e}")
        return f"<pre>Error loading panel: {str(e)}</pre>", 500
    finally:
        if conn:
            conn.close()


@panels_bp.route('/panel/planowane')
@login_required
def panel_planowane_page():
    """Panel planowanych dni wolnych."""
    planned = []
    try:
        if QueryHelper:
            planned = QueryHelper.get_planned_leaves(limit=500)
    except Exception:
        current_app.logger.exception('Failed loading planned leaves for full page')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('fragment') == 'true':
        return render_template('panels/planowane_panel.html', planned_leaves=planned)
    return render_template('panels_full/planowane_full.html', planned_leaves=planned)


@panels_bp.route('/panel/obecnosci')
@login_required
def panel_obecnosci_page():
    """Panel niedawnych nieobecności."""
    recent = []
    pracownicy = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        pracownicy = cursor.fetchall()
        conn.close()

        if QueryHelper:
            raw_recent = QueryHelper.get_recent_absences(days=30, limit=500)
            # Convert keys to match template: data_wpisu -> data, ilosc_godzin -> godziny
            recent = [{'id': r['id'], 'pracownik': r['pracownik'], 'typ': r['typ'], 'data': r['data_wpisu'], 'godziny': r['ilosc_godzin'], 'komentarz': r['komentarz']} for r in raw_recent]
    except Exception:
        current_app.logger.exception('Failed loading absences for full page')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('fragment') == 'true':
        return render_template('panels/obecnosci_panel.html', recent_absences=recent, pracownicy=pracownicy, dzisiaj=date.today())
    return render_template('panels_full/obecnosci_full.html', recent_absences=recent, pracownicy=pracownicy, dzisiaj=date.today())


@panels_bp.route('/panel/obsada')
@login_required
def panel_obsada_page():
    """Panel obsady - pełna strona z mapą pracowników."""
    sekcja = request.args.get('sekcja', 'Workowanie')
    date_str = request.args.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()

    obsady_map = {}
    wszyscy = []
    try:
        if QueryHelper:
            obsady_map = QueryHelper.get_obsada_for_date(qdate)
            wszyscy = QueryHelper.get_unassigned_pracownicy(qdate)
    except Exception:
        current_app.logger.exception('Failed loading obsada for panel page')

    return render_template('panels_full/obsada_full.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'))


@panels_bp.route('/panel_hours_page', methods=['GET'])
@login_required
@zarzad_required
def panel_hours_page():
    """Panel godzin pracy - podsumowanie godzin pracowników."""
    try:
        data_od = request.args.get('data_od', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        data_do = request.args.get('data_do', datetime.now().strftime('%Y-%m-%d'))
        
        # Build employee summary using the dedicated service function
        summary = build_employee_summary(data_od, data_do)
        
        # Build hours calendar data
        calendar_data = build_hours_calendar(data_od, data_do)
        
        return render_template('panel_hours.html', 
                              summary=summary, 
                              calendar_data=calendar_data,
                              data_od=data_od, 
                              data_do=data_do)
    
    except Exception as e:
        current_app.logger.error(f"Error loading panel_hours_page: {e}")
        return f"<pre>Error loading panel: {str(e)}</pre>", 500


@panels_bp.route('/panel_performance_page', methods=['GET'])
@login_required
@zarzad_required  
def panel_performance_page():
    """Panel wydajności - statystyki produkcyjne."""
    try:
        data_od = request.args.get('data_od', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        data_do = request.args.get('data_do', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get production statistics
        stats = {}
        
        # Orders completed
        cursor.execute("""
            SELECT COUNT(*) as total, SUM(tonaz_rzeczywisty) as total_tony 
            FROM plan_produkcji 
            WHERE status = 'zakończony' 
            AND data_planu BETWEEN %s AND %s
        """, (data_od, data_do))
        result = cursor.fetchone()
        stats['orders_completed'] = result['total'] or 0
        stats['total_tony'] = result['total_tony'] or 0
        
        # Get statistics by section
        cursor.execute("""
            SELECT sekcja, COUNT(*) as count, SUM(tonaz_rzeczywisty) as tony 
            FROM plan_produkcji 
            WHERE status = 'zakończony' 
            AND data_planu BETWEEN %s AND %s
            GROUP BY sekcja
        """, (data_od, data_do))
        stats['by_section'] = cursor.fetchall()
        
        conn.close()
        
        return render_template('panel_performance.html', 
                              stats=stats, 
                              data_od=data_od, 
                              data_do=data_do)
    
    except Exception as e:
        current_app.logger.error(f"Error loading panel_performance_page: {e}")
        return f"<pre>Error loading panel: {str(e)}</pre>", 500


@panels_bp.route('/moje_godziny')
@dynamic_role_required('moje_godziny')
def moje_godziny():
    """Pokaż podsumowanie godzin dla zalogowanego pracownika.
    
    Lider/admin mogą przeglądać wybranego pracownika przez query param 'pracownik_id'.
    """
    owner_pid = session.get('pracownik_id')
    # Normalize role from session (accept uppercase or mixed-case stored values)
    role = (session.get('rola') or '').lower()
    # If leader/admin and explicit pracownik_id given, allow viewing another pracownik
    viewed_pid = owner_pid
    if role in ['lider', 'admin', 'planista'] and request.args.get('pracownik_id'):
        try:
            viewed_pid = int(request.args.get('pracownik_id'))
        except Exception:
            viewed_pid = owner_pid

    # Jeśli konto nie ma powiązanego `pracownik_id`, pozwól liderowi/adminowi
    # zobaczyć stronę (wybór pracownika). Tylko zwykli użytkownicy bez mapowania
    # zobaczą komunikat o braku powiązania.
    if not owner_pid and role not in ['lider', 'admin', 'planista']:
        # Brak mapowania właściciela — poproś administratora o powiązanie konta
        fallback_summary = {'obecnosci': 0, 'typy': {}, 'wyjscia_hours': 0.0}
        return render_template('moje_godziny.html', mapped=False, owner_summary=fallback_summary, viewed_summary=None, d_od=None, d_do=None, wnioski=[], calendar_days_owner=[], calendar_days_viewed=None, pracownicy_list=None, selected_pid=None, owner_pid=None, viewed_pid=None)

    # Domyślny zakres: obecny miesiąc
    teraz = datetime.now()
    d_od = date(teraz.year, teraz.month, 1)
    d_do = date(teraz.year, teraz.month, teraz.day)

    conn = get_db_connection()
    cursor = conn.cursor()

    # If leader/admin, provide list of employees for selector
    pracownicy_list = None
    selected_pid = viewed_pid if viewed_pid != owner_pid else None
    try:
        if role in ['lider', 'admin']:
            cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
            pracownicy_list = cursor.fetchall()
    except Exception:
        pracownicy_list = None

    # Prepare summaries and lists for owner and (optionally) viewed employee
    def fetch_summary(prac_id):
        s = {'obecnosci': 0, 'typy': {}, 'wyjscia_hours': 0.0}
        try:
            cursor.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s", (prac_id, d_od, d_do))
            s['obecnosci'] = int(cursor.fetchone()[0] or 0)
        except Exception:
            s['obecnosci'] = 0
        try:
            cursor.execute("SELECT COALESCE(typ, ''), COALESCE(SUM(ilosc_godzin),0) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s GROUP BY typ", (prac_id, d_od, d_do))
            s['typy'] = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}
        except Exception:
            s['typy'] = {}
        try:
            cursor.execute("SELECT COALESCE(SUM(TIME_TO_SEC(wyjscie_do)-TIME_TO_SEC(wyjscie_od))/3600,0) FROM obecnosc WHERE pracownik_id=%s AND typ='Wyjscie prywatne' AND data_wpisu BETWEEN %s AND %s", (prac_id, d_od, d_do))
            s['wyjscia_hours'] = float(cursor.fetchone()[0] or 0)
        except Exception:
            s['wyjscia_hours'] = 0.0
        # Load leave counters from pracownicy if present
        try:
            cursor.execute("SELECT COALESCE(urlop_biezacy,0), COALESCE(urlop_zalegly,0) FROM pracownicy WHERE id=%s", (prac_id,))
            r = cursor.fetchone()
            s['urlop_biezacy'] = int(r[0] or 0) if r else 0
            s['urlop_zalegly'] = int(r[1] or 0) if r else 0
        except Exception:
            s['urlop_biezacy'] = 0
            s['urlop_zalegly'] = 0
        return s

    owner_summary = fetch_summary(owner_pid) if owner_pid else {'obecnosci': 0, 'typy': {}, 'wyjscia_hours': 0.0}
    viewed_summary = None
    if viewed_pid and viewed_pid != owner_pid:
        viewed_summary = fetch_summary(viewed_pid)

    # Pobierz wnioski złożone przez właściciela (do listy pod tabelą)
    try:
        cursor.execute("SELECT id, typ, data_od, data_do, czas_od, czas_do, powod, status, zlozono FROM wnioski_wolne WHERE pracownik_id=%s ORDER BY zlozono DESC", (owner_pid,))
        raw = cursor.fetchall()
        wnioski = []
        for r in raw:
            wnioski.append({
                'id': r[0], 'typ': r[1], 'data_od': r[2], 'data_do': r[3], 'czas_od': r[4], 'czas_do': r[5], 'powod': r[6], 'status': r[7], 'zlozono': r[8]
            })
    except Exception:
        wnioski = []

    # Pobierz nadgodziny złożone przez właściciela
    user_nadgodziny = []
    try:
        user_nadgodziny = OvertimeService.get_user_requests(owner_pid) if owner_pid else []
        current_app.logger.info(f"[DEBUG] moje_godziny: owner_pid={owner_pid}, user_nadgodziny count={len(user_nadgodziny)}")
    except Exception as e:
        current_app.logger.error(f"[DEBUG] Error fetching user_nadgodziny: {e}")
        user_nadgodziny = []

    # Pobierz oczekujące nadgodziny dla lidera
    pending_nadgodziny = []
    try:
        if role in ['lider', 'admin']:
            pending_nadgodziny = OvertimeService.get_pending_requests()
            current_app.logger.info(f"[DEBUG] moje_godziny: pending_nadgodziny count={len(pending_nadgodziny)}")
    except Exception as e:
        current_app.logger.error(f"[DEBUG] Error fetching pending_nadgodziny: {e}")
        pending_nadgodziny = []

    # Przygotuj dane kalendarza miesiąca: suma godzin na dzień, flaga HR, flaga zatwierdzenia
    try:
        year = d_od.year
        month = d_od.month
        import calendar
        _, days_in_month = calendar.monthrange(year, month)
        
        def build_calendar(prac_id):
            cal = []
            for day in range(1, days_in_month + 1):
                day_date = date(year, month, day)
                # suma godzin dla dnia
                cursor.execute("SELECT COALESCE(SUM(ilosc_godzin),0) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (prac_id, day_date))
                s = float(cursor.fetchone()[0] or 0)
                # czy są wpisy HR na ten dzień (typy HR/nieobecnosci)
                cursor.execute("SELECT COUNT(1) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s AND (typ LIKE '%%Nieobecno%%' OR typ LIKE '%%Urlop%%' OR typ LIKE '%%L4%%' OR typ LIKE '%%Nieobecnosc%%')", (prac_id, day_date))
                hr_count = int(cursor.fetchone()[0] or 0)
                # pobierz listę typów z tabeli obecnosc, by wyznaczyć krótki kod typu dla kalendarza
                cursor.execute("SELECT COALESCE(typ, '') FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (prac_id, day_date))
                typ_rows = [r[0] for r in cursor.fetchall()]
                typ_lower = ' '.join([str(t).lower() for t in typ_rows])
                # ustal etykietę krótką
                typ_label = ''
                if 'wyj' in typ_lower and 'prywat' in typ_lower:
                    typ_label = 'WP'
                elif 'odb' in typ_lower and 'godz' in typ_lower or 'odbior' in typ_lower:
                    typ_label = 'OG'
                elif 'opieka' in typ_lower:
                    typ_label = 'OP'
                elif 'urlop' in typ_lower:
                    typ_label = 'U'
                elif 'l4' in typ_lower or 'nieobec' in typ_lower:
                    typ_label = 'N'
                elif 'obec' in typ_lower:
                    typ_label = 'Obecny'
                else:
                    typ_label = ''
                # czy dzień został zatwierdzony przez lidera (raport końcowy) LUB istnieje zatwierdzony wniosek pokrywający ten dzień
                cursor.execute("SELECT COUNT(1) FROM raporty_koncowe WHERE data_raportu=%s", (day_date,))
                approved_report = int(cursor.fetchone()[0] or 0) > 0
                cursor.execute("SELECT COUNT(1) FROM wnioski_wolne WHERE pracownik_id=%s AND status='approved' AND data_od <= %s AND data_do >= %s", (prac_id, day_date, day_date))
                approved_wn = int(cursor.fetchone()[0] or 0) > 0
                approved = approved_report or approved_wn
                
                # Pobierz status urlopu na ten dzień (pending, approved, rejected, lub None)
                leave_status = None
                try:
                    cursor.execute("SELECT status FROM wnioski_wolne WHERE pracownik_id=%s AND data_od <= %s AND data_do >= %s ORDER BY zlozono DESC LIMIT 1", (prac_id, day_date, day_date))
                    result = cursor.fetchone()
                    if result:
                        leave_status = result[0]
                except Exception:
                    leave_status = None
                
                # Sprawdź czy pracownik ma przydzielenie do pracy na stanowisko w tym dniu
                assigned = False
                try:
                    cursor.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s", (prac_id, day_date))
                    assigned = int(cursor.fetchone()[0] or 0) > 0
                except Exception:
                    assigned = False
                
                # Pobierz zatwierdzonych nadgodzin na ten dzień
                nadgodziny_hours = 0.0
                try:
                    cursor.execute("SELECT COALESCE(SUM(ilosc_nadgodzin), 0) FROM nadgodziny WHERE pracownik_id=%s AND data=%s AND status='approved'", (prac_id, day_date))
                    nadgodziny_hours = float(cursor.fetchone()[0] or 0)
                except Exception:
                    nadgodziny_hours = 0.0
                
                cal.append({'date': day_date, 'hours': s, 'nadgodziny': nadgodziny_hours, 'total_hours': s + nadgodziny_hours, 'hr': hr_count > 0, 'approved': approved, 'typ_label': typ_label, 'leave_status': leave_status, 'assigned': assigned})
            return cal

        calendar_days_owner = build_calendar(owner_pid) if owner_pid else []
        calendar_days_viewed = None
        if viewed_pid and viewed_pid != owner_pid:
            calendar_days_viewed = build_calendar(viewed_pid)
    except Exception:
        calendar_days_owner = []
        calendar_days_viewed = None

    conn.close()

    return render_template('moje_godziny.html', mapped=True,
        owner_summary=owner_summary,
        viewed_summary=viewed_summary,
        d_od=d_od, d_do=d_do, wnioski=wnioski,
        user_nadgodziny=user_nadgodziny,
        pending_nadgodziny=pending_nadgodziny,
        calendar_days_owner=calendar_days_owner,
        calendar_days_viewed=calendar_days_viewed,
        pracownicy_list=pracownicy_list, selected_pid=selected_pid,
        owner_pid=owner_pid, viewed_pid=viewed_pid)
