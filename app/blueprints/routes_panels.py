from flask import Blueprint, render_template, request, redirect, session, current_app, send_file, url_for, jsonify
from datetime import date, datetime, timedelta
from collections import defaultdict
import json
import os
import calendar

from app.db import get_db_connection
from app.decorators import login_required, roles_required, zarzad_required

# Import QueryHelper if available for complex queries
try:
    from utils.query_helper import QueryHelper
except ImportError:
    QueryHelper = None

panels_bp = Blueprint('panels', __name__)


@panels_bp.route('/panel_wnioski_page', methods=['GET'])
@roles_required('lider', 'admin')
def panel_wnioski_page():
    """Pełnostronicowy widok zatwierdzeń wniosków."""
    wnioski = []
    try:
        if QueryHelper:
            raw_wnioski = QueryHelper.get_pending_leave_requests(limit=200)
            wnioski = raw_wnioski
    except Exception:
        current_app.logger.exception('Failed loading wnioski for full page')
    return render_template('panels_full/wnioski_full.html', wnioski=wnioski)


@panels_bp.route('/panel/planowane')
@login_required
def panel_planowane_page():
    """Panel planowanych dni wolnych."""
    planned = []
    try:
        if QueryHelper:
            planned = QueryHelper.get_planned_leaves(days_ahead=60, limit=500)
    except Exception:
        current_app.logger.exception('Failed loading planned leaves for full page')
    return render_template('panels_full/planowane_full.html', planned_leaves=planned)


@panels_bp.route('/panel/obecnosci')
@login_required
def panel_obecnosci_page():
    """Panel niedawnych nieobecności."""
    recent = []
    try:
        if QueryHelper:
            raw_recent = QueryHelper.get_recent_absences(days_back=30, limit=500)
            # Convert keys to match template: data_wpisu -> data, ilosc_godzin -> godziny
            recent = [{'id': r['id'], 'pracownik': r['pracownik'], 'typ': r['typ'], 'data': r['data_wpisu'], 'godziny': r['ilosc_godzin'], 'komentarz': r['komentarz']} for r in raw_recent]
    except Exception:
        current_app.logger.exception('Failed loading absences for full page')
    return render_template('panels_full/obecnosci_full.html', recent_absences=recent)


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


@panels_bp.route('/test-download')
@login_required
def test_download():
    """Strona testowa do pobrania raportów."""
    return render_template('test_download.html')


@panels_bp.route('/moje_godziny')
@login_required
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

    # Przygotuj dane kalendarza miesiąca: suma godzin na dzień, flaga HR, flaga zatwierdzenia
    try:
        year = d_od.year
        month = d_od.month
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
                cal.append({'date': day_date, 'hours': s, 'hr': hr_count > 0, 'approved': approved, 'typ_label': typ_label})
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
        calendar_days_owner=calendar_days_owner,
        calendar_days_viewed=calendar_days_viewed,
        pracownicy_list=pracownicy_list, selected_pid=selected_pid,
        owner_pid=owner_pid, viewed_pid=viewed_pid)


@panels_bp.route('/zarzad')
@zarzad_required
def zarzad_panel():
    """Management dashboard z KPI i chartami."""
    teraz = datetime.now()
    tryb = request.args.get('tryb', 'miesiac')
    
    def get_arg_int(key, default):
        try:
            return int(request.args.get(key))
        except Exception:
            return default
    
    wybrany_rok = get_arg_int('rok', teraz.year)
    wybrany_miesiac = get_arg_int('miesiac', teraz.month)
    wybrana_data = request.args.get('data') or str(teraz.date())
    
    if tryb == 'dzien':
        d_od = d_do = wybrana_data
        tytul = f"Dzienny: {wybrana_data}"
    elif tryb == 'rok':
        d_od = date(wybrany_rok, 1, 1)
        d_do = date(wybrany_rok, 12, 31)
        tytul = f"Roczny {wybrany_rok}"
    else:
        d_od = date(wybrany_rok, wybrany_miesiac, 1)
        d_do = (date(wybrany_rok, wybrany_miesiac+1, 1) - timedelta(days=1)) if wybrany_miesiac < 12 else date(wybrany_rok, 12, 31)
        tytul = f"Miesięczny ({wybrany_rok}-{wybrany_miesiac:02d})"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # KPI data
    cursor.execute("SELECT COALESCE(SUM(CASE WHEN sekcja='Zasyp' THEN tonaz ELSE 0 END), 0), COALESCE(SUM(CASE WHEN sekcja='Workowanie' THEN tonaz_rzeczywisty ELSE 0 END), 0), COUNT(id) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s AND status='zakonczone'", (d_od, d_do))
    kpi = cursor.fetchone()
    
    # Chart data
    cursor.execute("SELECT data_planu, SUM(CASE WHEN sekcja = 'Zasyp' THEN tonaz ELSE 0 END), SUM(CASE WHEN sekcja = 'Zasyp' THEN COALESCE(tonaz_rzeczywisty, 0) ELSE 0 END), SUM(CASE WHEN sekcja = 'Workowanie' THEN COALESCE(tonaz_rzeczywisty, 0) ELSE 0 END) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s GROUP BY data_planu ORDER BY data_planu", (d_od, d_do))
    ch = cursor.fetchall()
    ch_l = [str(r[0]) for r in ch]
    ch_plan = [float(r[1]) for r in ch]
    ch_zasyp = [float(r[2]) for r in ch]
    ch_work = [float(r[3]) for r in ch]
    
    # Pie chart data
    cursor.execute("SELECT kategoria, COALESCE(SUM(TIMESTAMPDIFF(MINUTE, czas_start, czas_stop)), 0) FROM dziennik_zmiany WHERE data_wpisu BETWEEN %s AND %s GROUP BY kategoria", (d_od, d_do))
    dt = cursor.fetchall()
    pie_l = [r[0] for r in dt]
    pie_v = [float(r[1]) for r in dt]
    
    # Personnel stats
    p_stats = []
    if tryb == 'dzien':
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        all_p = cursor.fetchall()
        p_dict = {p[1]: {'zasyp':'-','workowanie':'-','magazyn':'-','hr':'-'} for p in all_p}
        cursor.execute("SELECT p.imie_nazwisko, o.sekcja FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)) 
        for r in cursor.fetchall(): 
            p_dict[r[0]][r[1].lower()] = '✅'
        cursor.execute("SELECT p.imie_nazwisko, o.typ FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)) 
        for r in cursor.fetchall(): 
            p_dict[r[0]]['hr'] = r[1]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
    else:
        cursor.execute("SELECT p.imie_nazwisko, COUNT(o.id) FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko", (d_od, d_do))
        p_dict = defaultdict(lambda: {'total':0,'abs':0,'ot':0})
        for r in cursor.fetchall(): 
            p_dict[r[0]]['total'] = r[1]
        cursor.execute("SELECT p.imie_nazwisko, o.typ, SUM(o.ilosc_godzin) FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko, o.typ", (d_od, d_do))
        for r in cursor.fetchall(): 
            p_dict[r[0]]['abs' if r[1]=='Nieobecność' else 'ot'] = r[2]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
        p_stats.sort(key=lambda x: x['total'], reverse=True)
    
    conn.close()
    
    return render_template('zarzad.html', tryb=tryb, tytul=tytul, wybrany_rok=wybrany_rok, wybrany_miesiac=wybrany_miesiac, wybrana_data=wybrana_data, suma_plan=kpi[0], suma_wykonanie=kpi[1], ilosc_zlecen=kpi[2], procent=(kpi[1]/kpi[0]*100) if kpi[0] else 0, time_aw=sum(pie_v), chart_labels=json.dumps(ch_l), chart_plan=json.dumps(ch_plan), chart_zasyp=json.dumps(ch_zasyp), chart_work=json.dumps(ch_work), pie_labels=json.dumps(pie_l), pie_values=json.dumps(pie_v), pracownicy_stats=p_stats)


@panels_bp.route('/ustawienia')
@login_required
def ustawienia_app():
    """Fallback ustawienia route w blueprincie."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, label FROM roles ORDER BY id ASC")
            roles = cursor.fetchall()
        except Exception:
            roles = [('admin','admin'),('planista','planista'),('pracownik','pracownik'),('magazynier','magazynier'),('dur','dur'),('zarzad','zarzad'),('laboratorium','laboratorium')]
        conn.close()
        return render_template('ustawienia.html', roles=roles)
    except Exception:
        current_app.logger.exception('Failed to render ustawienia')
        return redirect('/')


@panels_bp.route('/pobierz_raport/<filename>')
@login_required
def pobierz_raport(filename):
    """Pobierz plik raportu z katalogu 'raporty'."""
    try:
        return send_file(os.path.join('raporty', filename), as_attachment=True)
    except Exception:
        return redirect('/')


@panels_bp.route('/pobierz_logi')
@roles_required('admin', 'zarzad')
def pobierz_logi():
    """Pobierz plik logów aplikacji (chronione - tylko admin i zarzad)."""
    log_path = os.path.join(os.path.dirname(__file__), 'logs', 'app.log')
    if not os.path.exists(log_path):
        return ("Brak logu", 404)
    return send_file(log_path, as_attachment=True)

