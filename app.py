from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
from waitress import serve
from datetime import date, datetime, timedelta
import json
from collections import defaultdict

from config import SECRET_KEY
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from db import get_db_connection, setup_database
from dto.paleta import PaletaDTO
from raporty import format_godziny
from routes_admin import admin_bp
from routes_api import api_bp, dodaj_plan_zaawansowany, dodaj_plan
from routes_planista import planista_bp
from decorators import login_required, zarzad_required, roles_required

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.add_extension('jinja2.ext.do')
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(planista_bp)
app.jinja_env.filters['format_czasu'] = format_godziny
setup_database()


# Backwards-compatible aliases for forms that post to root paths (keep working without reloading pages)
@app.route('/dodaj_plan_zaawansowany', methods=['POST'])
@login_required
def alias_dodaj_plan_zaawansowany():
    return dodaj_plan_zaawansowany()


@app.route('/dodaj_plan', methods=['POST'])
@login_required
def alias_dodaj_plan():
    return dodaj_plan()


@app.route('/zglos')
@login_required
def report_issue():
    sekcja = request.args.get('sekcja', 'Zasyp')
    now_time = datetime.now().strftime('%H:%M')
    return render_template('report_issue.html', sekcja=sekcja, now_time=now_time)


# Serve favicon at root to avoid 404s from some browsers
@app.route('/favicon.ico')
def favicon():
    try:
        return redirect(url_for('static', filename='favicon.svg'))
    except Exception:
        return ('', 204)


# Some devtools/extensions request a well-known file which we don't serve;
# respond with 204 No Content to avoid noisy 404/500 traces in logs.
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def _well_known_devtools():
    return ('', 204)

# Logging: zapisz pełne błędy do pliku logs/app.log
logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)
log_path = os.path.join(logs_dir, 'app.log')
handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s [pid=%(process)d]: %(message)s [in %(pathname)s:%(lineno)d]')
handler.setFormatter(formatter)
app.logger.setLevel(logging.DEBUG)
app.logger.addHandler(handler)
logging.getLogger('werkzeug').addHandler(handler)

# Logger dedykowany dla palet (przypomnienia)
palety_logger = logging.getLogger('palety_logger')
palety_logger.setLevel(logging.INFO)
palety_log_path = os.path.join(logs_dir, 'palety.log')
palety_handler = RotatingFileHandler(palety_log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
palety_handler.setLevel(logging.INFO)
palety_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
palety_handler.setFormatter(palety_formatter)
if not palety_logger.handlers:
    palety_logger.addHandler(palety_handler)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # Zarejestruj pełen traceback w logu i zwróć przyjazny komunikat użytkownikowi
    try:
        from flask import request
        app.logger.exception('Unhandled exception on %s %s: %s', request.method, request.path, error)
    except Exception:
        app.logger.exception('Unhandled exception: %s', error)
    return render_template('500.html') if os.path.exists(os.path.join(app.template_folder or '', '500.html')) else ("Wewnętrzny błąd serwera", 500)


def _cleanup_old_reports(folder='raporty', max_age_hours=24, interval_seconds=3600):
    """Wątek: usuwa pliki w `folder` starsze niż `max_age_hours` co `interval_seconds`."""
    try:
        while True:
            try:
                if os.path.exists(folder):
                    now = time.time()
                    max_age = max_age_hours * 3600
                    for name in os.listdir(folder):
                        path = os.path.join(folder, name)
                        try:
                            if os.path.isfile(path):
                                mtime = os.path.getmtime(path)
                                if now - mtime > max_age:
                                    try:
                                        os.remove(path)
                                        app.logger.info('Removed old report file: %s', path)
                                    except Exception:
                                        app.logger.exception('Failed to remove file: %s', path)
                        except Exception:
                            app.logger.exception('Error checking file: %s', path)
            except Exception:
                app.logger.exception('Error in cleanup loop')
            time.sleep(interval_seconds)
    except Exception:
        app.logger.exception('Cleanup thread terminating unexpectedly')


# Start cleanup thread (daemon) to remove old report files
try:
    cleanup_thread = threading.Thread(target=_cleanup_old_reports, kwargs={'folder':'raporty','max_age_hours':24,'interval_seconds':3600}, daemon=True)
    cleanup_thread.start()
except Exception:
    app.logger.exception('Failed to start cleanup thread')

# Monitor niepotwierdzonych palet (waga==0). Loguje przypomnienia, by nie duplikować
_reminded_palety = set()

def _monitor_unconfirmed_palety(threshold_minutes=10, interval_seconds=60):
    """Wątek sprawdzający palety bez wagi; loguje przypomnienie jeśli starsze niż threshold."""
    try:
        while True:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.waga = 0 AND COALESCE(pw.status,'') <> 'przyjeta' AND TIMESTAMPDIFF(MINUTE, pw.data_dodania, NOW()) >= %s",
                    (threshold_minutes,)
                )
                raw_rows = cursor.fetchall()
                # sformatuj daty w Pythonie — rozpakuj wyniki SELECT w oczekiwanym porządku
                rows = []
                for r in raw_rows:
                    try:
                        pid, plan_id, produkt, dt = r
                    except Exception:
                        # Fallback: użyj DTO jeśli kursor zwrócił nietypowy format
                        dto = PaletaDTO.from_db_row(r)
                        pid, plan_id, produkt, dt = dto.id, dto.plan_id, dto.produkt, dto.data_dodania
                    try:
                        sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                    except Exception:
                        sdt = str(dt)
                    rows.append((pid, plan_id, produkt, sdt))
                try:
                    conn.close()
                except Exception:
                    pass

                for r in rows:
                    try:
                        pid = r[0]
                        if pid in _reminded_palety:
                            continue
                        msg = f"Niepotwierdzona paleta id={r[0]}, plan_id={r[1]}, produkt={r[2]}, dodana={r[3]} - brak potwierdzenia > {threshold_minutes}min"
                        palety_logger.warning(msg)
                        app.logger.warning(msg)
                        _reminded_palety.add(pid)
                    except Exception:
                        app.logger.exception('Error processing unconfirmed paleta row')
            except Exception:
                app.logger.exception('Error in unconfirmed palety monitor loop')
            time.sleep(interval_seconds)
    except Exception:
        app.logger.exception('Unconfirmed palety monitor terminating unexpectedly')

try:
    # Testowy próg dla szybszego sprawdzenia: 1 minuta, interwał 15s
    palety_thread = threading.Thread(target=_monitor_unconfirmed_palety, kwargs={'threshold_minutes':1,'interval_seconds':15}, daemon=True)
    palety_thread.start()
except Exception:
    app.logger.exception('Failed to start palety monitor thread')



@app.before_request
def log_request_info():
    try:
        from flask import request
        # Skip noisy static file and well-known requests from debug logs to reduce noise
        p = request.path or ''
        if p.startswith('/static/') or p == '/favicon.ico' or p.startswith('/.well-known'):
            return
        # Use full_path to include query string, helps debugging links like ?sekcja=...
        full = getattr(request, 'full_path', None) or request.path
        try:
            import os as _os
            pid = _os.getpid()
        except Exception:
            pid = 'unknown'
        app.logger.debug('Incoming request (pid=%s): %s %s', pid, request.method, full)
    except Exception:
        pass


@app.after_request
def add_cache_headers(response):
    try:
        from flask import request
        p = request.path or ''
        # Add caching for static assets and favicon to reduce repeated requests
        if p.startswith('/static/') or p == '/favicon.ico' or p.startswith('/.well-known'):
            # cache for 1 day
            response.headers['Cache-Control'] = 'public, max-age=86400'
    except Exception:
        pass
    return response


@app.before_request
def ensure_pracownik_mapping():
    try:
        # If logged but no pracownik mapping in session, attempt to read from DB
        if session.get('zalogowany') and session.get('pracownik_id') is None and session.get('login'):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login=%s", (session.get('login'),))
            r = cursor.fetchone()
            try:
                if r and r[0] is not None:
                    session['pracownik_id'] = int(r[0])
                else:
                    # Try a best-effort automatic mapping on first login: tokenize login and search pracownicy
                    try:
                        import re
                        l = session.get('login').lower()
                        l_alpha = re.sub(r"[^a-ząćęłńóśżź ]+", ' ', l)
                        tokens = [t.strip() for t in re.split(r"\s+|[_\.\-]", l_alpha) if t.strip()]
                        if tokens:
                            where_clauses = " AND ".join(["LOWER(imie_nazwisko) LIKE %s" for _ in tokens])
                            params = tuple([f"%{t}%" for t in tokens])
                            q = f"SELECT id FROM pracownicy WHERE {where_clauses} LIMIT 2"
                            cursor.execute(q, params)
                            rows = cursor.fetchall()
                            if len(rows) == 1:
                                prac_id = int(rows[0][0])
                                try:
                                    cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (prac_id, session.get('login')))
                                    conn.commit()
                                    session['pracownik_id'] = prac_id
                                    try:
                                        app.logger.info('Auto-mapped login %s -> pracownik_id=%s', session.get('login'), prac_id)
                                    except Exception:
                                        pass
                                except Exception:
                                    try:
                                        conn.rollback()
                                    except Exception:
                                        pass
                    except Exception:
                        try:
                            app.logger.exception('Error during auto-mapping attempt')
                        except Exception:
                            pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    except Exception:
        try:
            app.logger.exception('Error ensuring pracownik mapping')
        except Exception:
            pass

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        # Pobierz opcjonalne pole pracownik_id by mapować konto na rekord pracownika
        cursor.execute("SELECT id, haslo, rola, COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login = %s", (request.form['login'],))
        row = cursor.fetchone()
        conn.close()
        if row:
            uid, hashed, rola, pracownik_id = row[0], row[1], row[2], row[3]
            if hashed and check_password_hash(hashed, request.form['haslo']):
                session['zalogowany'] = True
                # Normalize role to lowercase to avoid case-sensitivity issues in templates
                session['rola'] = (rola or '').lower()
                # Zapisz login i powiązanie pracownika w sesji (może być None)
                session['login'] = request.form['login']
                session['pracownik_id'] = int(pracownik_id) if pracownik_id is not None else None
                
                # Pobierz imię_nazwisko z tabeli pracownicy dla wyświetlenia w belce górnej
                imie_nazwisko = None
                if pracownik_id:
                    try:
                        conn2 = get_db_connection()
                        cursor2 = conn2.cursor()
                        cursor2.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                        p_row = cursor2.fetchone()
                        if p_row:
                            imie_nazwisko = p_row[0]
                        cursor2.close()
                        conn2.close()
                    except Exception:
                        pass
                session['imie_nazwisko'] = imie_nazwisko or request.form['login']
                # Use location.replace on client to avoid keeping login page in history
                target = '/planista' if rola == 'planista' else '/'
                html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>Logowanie...</title></head><body><script>window.location.replace('{target}');</script></body></html>"""
                resp = (html, 200)
                try:
                    from flask import make_response
                    resp = make_response(html)
                    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                    resp.headers['Pragma'] = 'no-cache'
                except Exception:
                    pass
                return resp
        flash("Błędne dane!", 'danger')
        return redirect('/login')
    # If already logged in, don't show login form — redirect to app
    if session.get('zalogowany'):
        return redirect('/')
    resp = render_template('login.html')
    try:
        from flask import make_response
        r = make_response(resp)
        r.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        r.headers['Pragma'] = 'no-cache'
        return r
    except Exception:
        return resp

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def index():
    aktywna_sekcja = request.args.get('sekcja', 'Zasyp')
    # normalize role for permission checks
    role = (session.get('rola') or '').lower()
    # Debug: log if open_stop present in URL params
    try:
        if request.args.get('open_stop') is not None:
            app.logger.info('index() called with open_stop=%s from %s', request.args.get('open_stop'), request.remote_addr)
    except Exception:
        app.logger.exception('Error while logging open_stop param')
    try:
        dzisiaj = datetime.strptime(request.args.get('data'), '%Y-%m-%d').date() if request.args.get('data') else date.today()
    except Exception:
        dzisiaj = date.today()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko")
    wszyscy = cursor.fetchall()
    cursor.execute("SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s", (dzisiaj,))
    zajeci_ids = [r[0] for r in cursor.fetchall()]
    dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
    cursor.execute("SELECT o.id, p.imie_nazwisko FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s AND o.sekcja = %s", (dzisiaj, aktywna_sekcja))
    obecna_obsada = cursor.fetchall()
    cursor.execute("SELECT d.id, p.imie_nazwisko, d.problem, TIME_FORMAT(d.czas_start, '%H:%i'), TIME_FORMAT(d.czas_stop, '%H:%i'), d.kategoria, TIMESTAMPDIFF(MINUTE, d.czas_start, d.czas_stop) FROM dziennik_zmiany d LEFT JOIN pracownicy p ON d.pracownik_id = p.id WHERE d.data_wpisu = %s AND d.sekcja = %s AND d.status='roboczy' ORDER BY d.id DESC", (dzisiaj, aktywna_sekcja))
    wpisy = cursor.fetchall()
    
    plan_dnia = []
    palety_mapa = {}
    magazyn_palety = []
    unconfirmed_palety = []
    suma_plan = 0
    suma_wykonanie = 0
    cursor.execute("SELECT DISTINCT produkt FROM plan_produkcji WHERE sekcja='Zasyp' AND status IN ('w toku', 'zakonczone') AND data_planu = %s", (dzisiaj,))
    zasyp_rozpoczete = [r[0] for r in cursor.fetchall()]
    
    if aktywna_sekcja == 'Magazyn':
        # Zwracamy kolumny w porządku zgodnym z PaletaDTO.from_db_row fallback:
        # (id, plan_id, waga, tara, waga_brutto, data_dodania, produkt, typ_produkcji)
        cursor.execute(
            "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
            "WHERE DATE(pw.data_dodania) = %s AND pw.waga > 0",
            (dzisiaj,)
        )
        raw_mag = cursor.fetchall()
        magazyn_palety = []
        for r in raw_mag:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            # include czas_potwierdzenia_s for display if present
            magazyn_palety.append((dto.produkt, dto.waga, sdt, dto.id, dto.plan_id, dto.status, dto.czas_potwierdzenia_s))
        # Pobierz niepotwierdzone palety (status != 'przyjeta'), by powiadomić magazyn jeśli nie potwierdzi w ciągu 10 minut
        # TYLKO z sekcji Magazyn - czyli tylko palety z Workowanie!
        try:
            cursor.execute("SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE DATE(pw.data_dodania) = %s AND p.sekcja = 'Workowanie' AND pw.waga > 0 AND COALESCE(pw.status,'') NOT IN ('przyjeta', 'zamknieta')", (dzisiaj,))
            raw = cursor.fetchall()
            out = []
            for r in raw:
                pid = r[0]
                plan_id = r[1]
                produkt = r[2]
                dt = r[3]
                try:
                    sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                except Exception:
                    sdt = str(dt)
                # compute sequence number of this paleta within its plan (1-based)
                try:
                    cursor.execute("SELECT COUNT(1) FROM palety_workowanie WHERE plan_id = %s AND id <= %s", (plan_id, pid))
                    seq_row = cursor.fetchone()
                    seq = int(seq_row[0]) if seq_row and seq_row[0] is not None else 1
                except Exception:
                    seq = None
                # compute elapsed time since creation
                try:
                    from datetime import datetime as _dt
                    now = _dt.now()
                    if hasattr(dt, 'strftime'):
                        delta = now - dt
                    else:
                        try:
                            parsed = _dt.strptime(str(dt), '%Y-%m-%d %H:%M:%S')
                            delta = now - parsed
                        except Exception:
                            delta = None
                    if delta:
                        secs = int(delta.total_seconds())
                        h = secs // 3600
                        m = (secs % 3600) // 60
                        s = secs % 60
                        if h > 0:
                            elapsed = f"{h}h {m:02d}m"
                        elif m > 0:
                            elapsed = f"{m}m {s:02d}s"
                        else:
                            elapsed = f"{s}s"
                    else:
                        elapsed = ''
                except Exception:
                    elapsed = ''
                out.append((pid, plan_id, produkt, sdt, seq, elapsed))
            unconfirmed_palety = out
        except Exception:
            unconfirmed_palety = []

    cursor.execute("SELECT id, produkt, tonaz, status, TIME_FORMAT(real_start, '%H:%i'), TIME_FORMAT(real_stop, '%H:%i'), TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci FROM plan_produkcji WHERE data_planu = %s AND sekcja = %s AND status != 'nieoplacone' ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, kolejnosc ASC, id ASC", (dzisiaj, aktywna_sekcja))
    plan_dnia = [list(r) for r in cursor.fetchall()]
    
    for p in plan_dnia:
        if p[7] is None: p[7] = 0
        # Rozpoznaj zlecenia jakościowe (nie wliczane do produkcji)
        produkt_lower = str(p[1]).strip().lower() if p[1] else ''
        # Najpierw sprawdź pole typ_zlecenia w DB (jeśli dostępne), fallback do nazwy produktu
        is_quality = False
        try:
            cursor.execute("SELECT COALESCE(typ_zlecenia, ''), sekcja FROM plan_produkcji WHERE id=%s", (p[0],))
            rz = cursor.fetchone()
            if rz and (str(rz[0]).strip().lower() == 'jakosc' or (len(rz) > 1 and str(rz[1]).strip() == 'Jakosc')):
                is_quality = True
        except Exception:
            pass
        if not is_quality:
            if produkt_lower in ['dezynfekcja linii', 'dezynfekcja']:
                is_quality = True

        if not is_quality:
            suma_plan += p[2] if p[2] else 0

        current_wykonanie = p[7]

        if aktywna_sekcja == 'Magazyn':
            # Zapytanie zwraca kolumny w kolejności zgodnej z PaletaDTO
            cursor.execute(
                "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
                "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
                "WHERE p.data_planu = %s AND p.produkt = %s AND p.sekcja = 'Workowanie' ORDER BY pw.id DESC",
                (dzisiaj, p[1])
            )
            raw_pal = cursor.fetchall()
            palety = []
            for r in raw_pal:
                dto = PaletaDTO.from_db_row(r)
                dt = dto.data_dodania
                try:
                    sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
                    sdt_full = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                except Exception:
                    sdt = str(dt)
                    sdt_full = str(dt)
                # format czas_potwierdzenia_s for display
                cps = None
                try:
                    if dto.czas_potwierdzenia_s is not None:
                        secs = int(dto.czas_potwierdzenia_s)
                        if secs >= 3600:
                            cps = f"{secs//3600}h { (secs%3600)//60:02d }m"
                        elif secs >= 60:
                            cps = f"{secs//60}m { secs%60:02d }s"
                        else:
                            cps = f"{secs}s"
                except Exception:
                    cps = None
                palety.append((dto.waga, sdt, dto.id, dto.plan_id, dto.typ_produkcji, dto.tara, dto.waga_brutto, dto.status, cps, sdt_full))
            palety_mapa[p[0]] = palety
            # SUMA W KG (BEZ DZIELENIA)
            waga_kg = sum(pal[0] for pal in palety)
            p[7] = waga_kg
            if not is_quality:
                suma_wykonanie += waga_kg
        elif aktywna_sekcja in ('Workowanie', 'Zasyp'):
            cursor.execute(
                "SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
                "FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id "
                "WHERE pw.plan_id = %s ORDER BY pw.id DESC",
                (p[0],)
            )
            raw_pal = cursor.fetchall()
            palety = []
            for r in raw_pal:
                dto = PaletaDTO.from_db_row(r)
                dt = dto.data_dodania
                try:
                    sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
                    sdt_full = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                except Exception:
                    sdt = str(dt)
                    sdt_full = str(dt)
                cps = None
                try:
                    if dto.czas_potwierdzenia_s is not None:
                        secs = int(dto.czas_potwierdzenia_s)
                        if secs >= 3600:
                            cps = f"{secs//3600}h { (secs%3600)//60:02d }m"
                        elif secs >= 60:
                            cps = f"{secs//60}m { secs%60:02d }s"
                        else:
                            cps = f"{secs}s"
                except Exception:
                    cps = None
                palety.append((dto.waga, sdt, dto.id, dto.plan_id, dto.typ_produkcji, dto.tara, dto.waga_brutto, dto.status, cps, sdt_full))
            palety_mapa[p[0]] = palety
            if not is_quality:
                suma_wykonanie += current_wykonanie
        else:
            if not is_quality:
                suma_wykonanie += current_wykonanie

        waga_workowania = 0
        diff = 0
        alert = False
        if aktywna_sekcja == 'Zasyp':
            cursor.execute("SELECT SUM(tonaz_rzeczywisty) FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND typ_produkcji=%s", (dzisiaj, p[1], p[9]))
            res = cursor.fetchone()
            waga_workowania = res[0] if res and res[0] else 0
            if p[7]:
                diff = p[7] - waga_workowania
                if abs(diff) > 10: alert = True # Tolerancja 10kg
        p.extend([waga_workowania, diff, alert])

    next_workowanie_id = None
    if aktywna_sekcja == 'Workowanie':
        kandydaci = [p for p in plan_dnia if p[3] == 'zaplanowane']
        kandydaci.sort(key=lambda x: x[0])
        if kandydaci: next_workowanie_id = kandydaci[0][0]

    # Spróbuj pobrać nowe kolumny `wyjscie_od/wyjscie_do`; jeśli ich nie ma w DB,
    # złap wyjątek i wykonaj zapytanie bez nich, dokładając None jako fallback.
    try:
        cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz, o.wyjscie_od, o.wyjscie_do FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (dzisiaj,))
        raporty_hr = cursor.fetchall()
    except Exception as e:
        try:
            app.logger.warning('Falling back to legacy obecnosc SELECT (missing columns?): %s', e)
        except Exception:
            pass
        try:
            cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (dzisiaj,))
            rows = cursor.fetchall()
            # Dołóż pola wyjscie_od/wyjscie_do jako None, żeby szablon nie zawodził
            raporty_hr = [tuple(list(r) + [None, None]) for r in rows]
        except Exception:
            app.logger.exception('Failed to fetch obecnosc rows')
            raporty_hr = []

    # Przygotuj listę pracowników dostępnych do nadgodzin: wyklucz tych, którzy mają wpis w obecnosc
    try:
        cursor.execute("SELECT pracownik_id, typ FROM obecnosc WHERE data_wpisu = %s", (dzisiaj,))
        ob = cursor.fetchall()
        # Wszystkie osoby z wpisem w obecnosc (dowolny typ)
        ob_all_ids = set(r[0] for r in ob)
        # Osoby z nie-prywatnymi nieobecnościami (do wykluczenia z nadgodzin)
        ob_nonprivate_ids = set(r[0] for r in ob if str(r[1]).strip().lower() != 'wyjscie prywatne')
        # HR: lista pracowników dostępnych do nadgodzin (wyklucz nie-private)
        hr_dostepni = [p for p in wszyscy if p[0] not in ob_nonprivate_ids]
        # HR: lista pracowników do formularza Nieobecności — nie pokazuj tych, którzy już mają wpis
        # Również wyklucz osoby przypisane do stanowisk (obsada)
        hr_pracownicy = [p for p in wszyscy if p[0] not in ob_all_ids and p[0] not in zajeci_ids]
    except Exception:
        # Fallback: ukryj przynajmniej osoby przypisane do obsady
        try:
            hr_dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
            hr_pracownicy = [p for p in wszyscy if p[0] not in zajeci_ids]
        except Exception:
            hr_dostepni = wszyscy
            hr_pracownicy = wszyscy

    # Liczba zleceń jakościowych zgłoszonych przez laboratorium (nieprodukcyjne)
    try:
        cursor.execute("SELECT COUNT(1) FROM plan_produkcji WHERE (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone'")
        quality_count = int(cursor.fetchone()[0] or 0)
    except Exception:
        quality_count = 0

    # If user is leader/admin, fetch recent pending leave requests for dashboard
    wnioski_pending = []
    try:
        if role in ['lider', 'admin']:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.powod, w.zlozono FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id WHERE w.status = 'pending' ORDER BY w.zlozono DESC LIMIT 50")
            raw = cursor.fetchall()
            for r in raw:
                wnioski_pending.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3], 'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'powod': r[7], 'zlozono': r[8]})
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        try:
            app.logger.exception('Failed to fetch pending wnioski for dashboard')
        except Exception:
            pass

    # Pobierz planowane urlopy (następne 60 dni)
    planned_leaves = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        end_date = date.today() + timedelta(days=60)
        cursor.execute("SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.status FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id WHERE w.data_od <= %s AND w.data_do >= %s ORDER BY w.data_od ASC LIMIT 500", (end_date, date.today()))
        raw = cursor.fetchall()
        for r in raw:
            planned_leaves.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3], 'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'status': r[7]})
        try:
            conn.close()
        except Exception:
            pass
    except Exception:
        try:
            app.logger.exception('Failed to fetch planned leaves')
        except Exception:
            pass

    # Pobierz ostatnie nieobecności (ostatnie 30 dni)
    recent_absences = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        since = date.today() - timedelta(days=30)
        cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu BETWEEN %s AND %s ORDER BY o.data_wpisu DESC LIMIT 500", (since, date.today()))
        raw = cursor.fetchall()
        for r in raw:
            recent_absences.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data': r[3], 'godziny': r[4], 'komentarz': r[5]})
        try:
            conn.close()
        except Exception:
            pass
    except Exception:
        try:
            app.logger.exception('Failed to fetch recent absences')
        except Exception:
            pass

    # Wczytaj notatki zmianowe z bazy danych (fallback do pustej listy)
    shift_notes = []
    try:
        # Create fresh connection for shift_notes to avoid connection issues
        try:
            conn_notes = get_db_connection()
            cursor_notes = conn_notes.cursor()
            try:
                cursor_notes.execute("""
                    CREATE TABLE IF NOT EXISTS shift_notes (
                        id BIGINT PRIMARY KEY,
                        pracownik_id INT,
                        note TEXT,
                        author VARCHAR(255),
                        date DATE,
                        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
            except Exception:
                # table creation may fail on some environments, ignore
                pass
            try:
                cursor_notes.execute("SELECT id, pracownik_id, DATE_FORMAT(date, '%Y-%m-%d'), note, author, created FROM shift_notes ORDER BY created DESC LIMIT 200")
                rows = cursor_notes.fetchall()
                app.logger.info('Loaded %d shift notes from database', len(rows) if rows else 0)
                for r in rows:
                    shift_notes.append({'id': r[0], 'pracownik_id': r[1], 'date': r[2], 'note': r[3], 'author': r[4], 'created': r[5]})
            except Exception as e:
                app.logger.exception('Failed to load shift notes: %s', str(e))
                shift_notes = []
            try:
                conn_notes.close()
            except Exception:
                pass
        except Exception:
            try:
                app.logger.exception('Failed to load shift notes from DB')
            except Exception:
                pass
    except Exception:
        try:
            app.logger.exception('Error in shift_notes loading block')
        except Exception:
            pass

    conn.close()
    try:
        app.logger.info('Rendering index: sekcja=%s plans=%d palety_map_keys=%d unconfirmed_palety=%d open_stop=%s shift_notes_count=%d', aktywna_sekcja, len(plan_dnia) if plan_dnia is not None else 0, len(palety_mapa.keys()) if isinstance(palety_mapa, dict) else 0, len(unconfirmed_palety) if hasattr(unconfirmed_palety, '__len__') else 0, request.args.get('open_stop'), len(shift_notes) if shift_notes else 0)
    except Exception:
        app.logger.exception('Error logging index render info')

    # If explicit sekcja query param provided, render the original production dashboard view
    # so links like ?sekcja=Zasyp / Workowanie / Magazyn behave as before.
    try:
        if 'sekcja' in request.args:
            return render_template('dashboard.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada, wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety, unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr, zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id, now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count, wnioski_pending=wnioski_pending)
    except Exception:
        app.logger.exception('Failed rendering production dashboard, falling back to global')

    return render_template('dashboard_global.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada, wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety, unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr, zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id, now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count, wnioski_pending=wnioski_pending, planned_leaves=planned_leaves, recent_absences=recent_absences, shift_notes=shift_notes)


@app.route('/moje_godziny')
@login_required
def moje_godziny():
    # Pokaż podsumowanie godzin dla zalogowanego pracownika.
    # Lider/admin mogą przeglądać wybranego pracownika przez query param 'pracownik_id'.
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
        return render_template('moje_godziny.html', mapped=False, owner_summary=fallback_summary, viewed_summary=None, d_od=d_od if 'd_od' in locals() else None, d_do=d_do if 'd_do' in locals() else None, wnioski=[], calendar_days_owner=[], calendar_days_viewed=None, pracownicy_list=None, selected_pid=None, owner_pid=None, viewed_pid=None)

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

    # Przygotuj dane kalendarza miesiąca: suma godzin na dzień, flaga HR (L4/Urlop itp.), flaga zatwierdzenia przez lidera
    try:
        import calendar
        year = d_od.year
        month = d_od.month
        _, days_in_month = calendar.monthrange(year, month)
        calendar_days = []
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

@app.route('/zarzad')
@zarzad_required
def zarzad_panel():
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
    cursor.execute("SELECT COALESCE(SUM(CASE WHEN sekcja='Zasyp' THEN tonaz ELSE 0 END), 0), COALESCE(SUM(CASE WHEN sekcja='Workowanie' THEN tonaz_rzeczywisty ELSE 0 END), 0), COUNT(id) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s AND status='zakonczone'", (d_od, d_do))
    kpi = cursor.fetchone()
    cursor.execute("SELECT data_planu, SUM(CASE WHEN sekcja = 'Zasyp' THEN tonaz ELSE 0 END), SUM(CASE WHEN sekcja = 'Zasyp' THEN COALESCE(tonaz_rzeczywisty, 0) ELSE 0 END), SUM(CASE WHEN sekcja = 'Workowanie' THEN COALESCE(tonaz_rzeczywisty, 0) ELSE 0 END) FROM plan_produkcji WHERE data_planu BETWEEN %s AND %s GROUP BY data_planu ORDER BY data_planu", (d_od, d_do))
    ch = cursor.fetchall()
    ch_l = [str(r[0]) for r in ch]
    ch_plan = [float(r[1]) for r in ch]
    ch_zasyp = [float(r[2]) for r in ch]
    ch_work = [float(r[3]) for r in ch]
    cursor.execute("SELECT kategoria, COALESCE(SUM(TIMESTAMPDIFF(MINUTE, czas_start, czas_stop)), 0) FROM dziennik_zmiany WHERE data_wpisu BETWEEN %s AND %s GROUP BY kategoria", (d_od, d_do))
    dt = cursor.fetchall()
    pie_l = [r[0] for r in dt]
    pie_v = [float(r[1]) for r in dt]
    p_stats = []
    if tryb == 'dzien':
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        all_p = cursor.fetchall()
        p_dict = {p[1]: {'zasyp':'-','workowanie':'-','magazyn':'-','hr':'-'} for p in all_p}
        cursor.execute("SELECT p.imie_nazwisko, o.sekcja FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)) 
        for r in cursor.fetchall(): p_dict[r[0]][r[1].lower()] = '✅'
        cursor.execute("SELECT p.imie_nazwisko, o.typ FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu=%s", (d_od,)) 
        for r in cursor.fetchall(): p_dict[r[0]]['hr'] = r[1]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
    else:
        cursor.execute("SELECT p.imie_nazwisko, COUNT(o.id) FROM obsada_zmiany o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko", (d_od, d_do))
        p_dict = defaultdict(lambda: {'total':0,'abs':0,'ot':0})
        for r in cursor.fetchall(): p_dict[r[0]]['total'] = r[1]
        cursor.execute("SELECT p.imie_nazwisko, o.typ, SUM(o.ilosc_godzin) FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu BETWEEN %s AND %s GROUP BY p.imie_nazwisko, o.typ", (d_od, d_do))
        for r in cursor.fetchall(): p_dict[r[0]]['abs' if r[1]=='Nieobecność' else 'ot'] = r[2]
        p_stats = [{'name': k, **v} for k, v in p_dict.items()]
        p_stats.sort(key=lambda x: x['total'], reverse=True)
    conn.close()
    return render_template('zarzad.html', tryb=tryb, tytul=tytul, wybrany_rok=wybrany_rok, wybrany_miesiac=wybrany_miesiac, wybrana_data=wybrana_data, suma_plan=kpi[0], suma_wykonanie=kpi[1], ilosc_zlecen=kpi[2], procent=(kpi[1]/kpi[0]*100) if kpi[0] else 0, time_aw=sum(pie_v), chart_labels=json.dumps(ch_l), chart_plan=json.dumps(ch_plan), chart_zasyp=json.dumps(ch_zasyp), chart_work=json.dumps(ch_work), pie_labels=json.dumps(pie_l), pie_values=json.dumps(pie_v), pracownicy_stats=p_stats)


@app.route('/dur/awarie')
@roles_required('dur', 'admin', 'zarzad')
def dur_awarie():
    """DUR - przegląd i zatwierdzanie awarii"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz wszystkie awarie z ostatnich 30 dni
        query = """
            SELECT 
                id, 
                data_wpisu, 
                sekcja, 
                kategoria, 
                problem, 
                status, 
                czas_start, 
                czas_stop,
                pracownik_id
            FROM dziennik_zmiany 
            WHERE data_wpisu >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ORDER BY data_wpisu DESC, czas_start DESC
        """
        cursor.execute(query)
        awarie = cursor.fetchall()
        
        # Pobierz pracowników do wyświetlenia
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        pracownicy_raw = cursor.fetchall()
        pracownicy_map = {r['id']: r['imie_nazwisko'] for r in pracownicy_raw} if pracownicy_raw else {}
        
        cursor.close()
        conn.close()
        
        # Mapuj pracownika do każdej awarii i pobierz komentarze
        for awaria in awarie:
            awaria['pracownik_name'] = pracownicy_map.get(awaria['pracownik_id'], 'Nieznany')
            # Konwertuj timedelta na godziny:minuty
            if awaria['czas_start']:
                h, remainder = divmod(int(awaria['czas_start'].total_seconds()), 3600)
                m = remainder // 60
                awaria['czas_start_str'] = f"{h:02d}:{m:02d}"
            else:
                awaria['czas_start_str'] = '??:??'
            
            if awaria['czas_stop']:
                h, remainder = divmod(int(awaria['czas_stop'].total_seconds()), 3600)
                m = remainder // 60
                awaria['czas_stop_str'] = f"{h:02d}:{m:02d}"
            else:
                awaria['czas_stop_str'] = '??:??'
            
            # Pobierz komentarze do tej awarii
            conn_kom = get_db_connection()
            cursor_kom = conn_kom.cursor(dictionary=True)
            cursor_kom.execute("""
                SELECT dk.id, dk.tresc, dk.created_at, p.imie_nazwisko 
                FROM dur_komentarze dk 
                LEFT JOIN pracownicy p ON dk.autor_id = p.id 
                WHERE dk.awaria_id = %s 
                ORDER BY dk.created_at DESC
            """, (awaria['id'],))
            awaria['komentarze'] = cursor_kom.fetchall()
            cursor_kom.close()
            conn_kom.close()
        
        return render_template('dur_awarie.html', awarie=awarie)
    except Exception as e:
        app.logger.exception(f'Error in dur_awarie: {e}')
        flash('⚠️ Błąd przy wczytywaniu awarii', 'error')
        return redirect('/')


@app.route('/api/dur/zatwierdz_awarię/<int:awaria_id>', methods=['POST'])
@roles_required('dur', 'admin', 'zarzad')
def dur_zatwierdz_awarię(awaria_id):
    """Zatwierdź awarie - zmień status, czas_stop i dodaj komentarz"""
    try:
        status = request.form.get('status', 'zatwierdzone')  # zatwierdzone, odrzucone
        czas_stop_str = request.form.get('czas_stop', '').strip()  # np. "23:45:00"
        komentarz = request.form.get('komentarz', '').strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Aktualizuj status i czas_stop
        update_fields = ["status = %s"]
        update_values = [status]
        
        if czas_stop_str:
            # Konwertuj string czasu na format MySQL TIME
            update_fields.append("czas_stop = %s")
            update_values.append(czas_stop_str)
        
        update_values.append(awaria_id)
        sql = f"UPDATE dziennik_zmiany SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(sql, update_values)
        conn.commit()
        
        # 2. Dodaj komentarz jeśli jest wpisany
        if komentarz:
            pracownik_id = session.get('pracownik_id')
            cursor.execute(
                "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
                (awaria_id, pracownik_id, komentarz)
            )
            conn.commit()
        
        cursor.close()
        conn.close()
        
        msg = f'✓ Awaria #{awaria_id} zmieniona na: {status}'
        if czas_stop_str:
            msg += f' (czas_stop: {czas_stop_str})'
        flash(msg, 'success')
        return redirect(request.referrer or '/dur/awarie')
    except Exception as e:
        app.logger.exception(f'Error in dur_zatwierdz_awarię: {e}')
        flash('⚠️ Błąd przy zatwierdzaniu awarii', 'error')
        return redirect('/dur/awarie')


@app.route('/ustawienia')
@login_required
def ustawienia_app():
    """Fallback ustawienia route w `app.py` na wypadek braku rejestracji w blueprintach."""
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
        app.logger.exception('Failed to render ustawienia')
        return redirect('/')

@app.route('/pobierz_raport/<filename>')
@login_required
def pobierz_raport(filename): return send_file(os.path.join('raporty', filename), as_attachment=True)


@app.route('/jakosc')
@roles_required('laboratorium', 'lider', 'zarzad', 'admin', 'planista')
def jakosc_index():
    """Lista zleceń jakościowych (typ_zlecenia = 'jakosc')."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, produkt, data_planu, sekcja, tonaz, status, TIME_FORMAT(real_start, '%H:%i'), TIME_FORMAT(real_stop, '%H:%i'), tonaz_rzeczywisty
            FROM plan_produkcji
            WHERE COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc'
            ORDER BY data_planu DESC, id DESC
        """)
        zlecenia = cursor.fetchall()
        conn.close()
        return render_template('jakosc.html', zlecenia=zlecenia, rola=session.get('rola'))
    except Exception:
        app.logger.exception('Failed to render /jakosc')
        return redirect('/')


@app.route('/jakosc/dodaj', methods=['POST'])
@roles_required('laboratorium', 'lider', 'zarzad', 'admin')
def jakosc_dodaj():
    """Utwórz nowe zlecenie jakościowe (sekcja 'Jakosc', typ_zlecenia='jakosc')."""
    try:
        produkt = request.form.get('produkt')
        if not produkt:
            flash('Podaj nazwę produktu', 'warning')
            return redirect(url_for('jakosc_index'))
        data_planu = request.form.get('data_planu') or str(date.today())
        try:
            tonaz = int(float(request.form.get('tonaz') or 0))
        except Exception:
            tonaz = 0
        typ = request.form.get('typ_produkcji') or 'standard'

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
        res = cursor.fetchone()
        nk = (res[0] if res and res[0] else 0) + 1
        cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, typ_zlecenia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', 'Jakosc', nk, typ, 'jakosc'))
        conn.commit()
        conn.close()
        flash('Zlecenie jakościowe utworzone', 'success')
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        app.logger.exception('Failed to create jakosc order')
        flash('Błąd podczas tworzenia zlecenia jakościowego', 'danger')
    return redirect(url_for('jakosc_index'))


@app.route('/add_shift_note', methods=['POST'])
@login_required
def add_shift_note():
    try:
        note = request.form.get('note', '').strip()
        pracownik_id = request.form.get('pracownik_id') or None
        date_str = request.form.get('date') or str(date.today())
        author = session.get('login') or 'unknown'

        app.logger.info('add_shift_note: note=%s, pracownik_id=%s, date=%s, author=%s', note[:50] if note else '', pracownik_id, date_str, author)

        # Ensure shift_notes table exists and insert record
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shift_notes (
                    id BIGINT PRIMARY KEY,
                    pracownik_id INT,
                    note TEXT,
                    author VARCHAR(255),
                    date DATE,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        except Exception:
            # ignore create table errors
            pass
        nid = int(time.time() * 1000)  # Use milliseconds for uniqueness
        try:
            cursor.execute("INSERT INTO shift_notes (id, pracownik_id, note, author, date) VALUES (%s, %s, %s, %s, %s)", (nid, pracownik_id, note, author, date_str))
            conn.commit()
            app.logger.info('Note saved successfully: id=%s', nid)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            app.logger.exception('Failed to insert shift note into DB: %s', str(e))
        try:
            conn.close()
        except Exception:
            pass
        try:
            flash('✅ Notatka zapisana', 'success')
        except Exception:
            pass
    except Exception:
        try:
            app.logger.exception('Error in add_shift_note')
        except Exception:
            pass
    return redirect('/')


@app.route('/api/shift_note/<int:note_id>/delete', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def delete_shift_note(note_id):
    """Usuń notatkę zmianową"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy notatka należy do zalogowanego użytkownika lub jest admin
        cursor.execute("SELECT author FROM shift_notes WHERE id = %s", (note_id,))
        row = cursor.fetchone()
        author = session.get('login') or 'unknown'
        if row and (row[0] == author or session.get('rola') == 'admin'):
            cursor.execute("DELETE FROM shift_notes WHERE id = %s", (note_id,))
            conn.commit()
            try:
                flash('Notatka usunięta', 'success')
            except Exception:
                pass
        else:
            try:
                flash('Brak uprawnień do usunięcia notatki', 'danger')
            except Exception:
                pass
        conn.close()
    except Exception:
        try:
            app.logger.exception('Error deleting shift note')
        except Exception:
            pass
    return redirect('/')


@app.route('/api/shift_note/<int:note_id>/update', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def update_shift_note(note_id):
    """Edytuj notatkę zmianową"""
    try:
        note_text = request.form.get('note', '').strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy notatka należy do zalogowanego użytkownika lub jest admin
        cursor.execute("SELECT author FROM shift_notes WHERE id = %s", (note_id,))
        row = cursor.fetchone()
        author = session.get('login') or 'unknown'
        if row and (row[0] == author or session.get('rola') == 'admin'):
            cursor.execute("UPDATE shift_notes SET note = %s WHERE id = %s", (note_text, note_id))
            conn.commit()
            try:
                flash('Notatka zaktualizowana', 'success')
            except Exception:
                pass
        else:
            try:
                flash('Brak uprawnień do edycji notatki', 'danger')
            except Exception:
                pass
        conn.close()
    except Exception:
        try:
            app.logger.exception('Error updating shift note')
        except Exception:
            pass
    return redirect('/')


@app.route('/jakosc/<int:plan_id>', methods=['GET', 'POST'])
@roles_required('laboratorium', 'lider', 'zarzad', 'admin', 'planista')
def jakosc_detail(plan_id):
    """Szczegóły zlecenia jakościowego i upload dokumentów."""
    docs_dir = os.path.join('raporty', 'jakosc_docs', str(plan_id))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, produkt, data_planu, sekcja, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, wyjasnienie_rozbieznosci FROM plan_produkcji WHERE id=%s", (plan_id,))
        plan = cursor.fetchone()
        conn.close()

        if request.method == 'POST':
            # Tylko role laboratorum/lider/zarzad/admin mogą przesyłać pliki.
            if session.get('rola') not in ['laboratorium', 'lider', 'zarzad', 'admin']:
                flash('Brak uprawnień do przesyłania plików', 'danger')
                return redirect(url_for('jakosc_detail', plan_id=plan_id))
            f = request.files.get('file')
            if f and f.filename:
                filename = secure_filename(f.filename)
                os.makedirs(docs_dir, exist_ok=True)
                save_path = os.path.join(docs_dir, filename)
                f.save(save_path)
                flash('Plik przesłany', 'success')
            else:
                flash('Brak pliku do przesłania', 'warning')
            return redirect(url_for('jakosc_detail', plan_id=plan_id))

        files = []
        if os.path.exists(docs_dir):
            files = sorted(os.listdir(docs_dir), reverse=True)

        return render_template('jakosc_detail.html', plan=plan, files=files, plan_id=plan_id, rola=session.get('rola'))
    except Exception:
        app.logger.exception('Failed to render /jakosc/%s', plan_id)
        return redirect('/jakosc')


@app.route('/jakosc/download/<int:plan_id>/<path:filename>')
@roles_required('laboratorium', 'lider', 'zarzad', 'admin', 'planista')
def jakosc_download(plan_id, filename):
    docs_dir = os.path.join('raporty', 'jakosc_docs', str(plan_id))
    file_path = os.path.join(docs_dir, filename)
    if not os.path.exists(file_path):
        return ("Plik nie znaleziony", 404)
    return send_file(file_path, as_attachment=True)


@app.route('/pobierz_logi')
@roles_required('admin', 'zarzad')
def pobierz_logi():
    """Tymczasowy, chroniony endpoint do pobrania pliku logów aplikacji.

    Dostęp: tylko role 'admin' i 'zarzad'. Zwraca `app.log` jako załącznik.
    """
    log_path = os.path.join(os.path.dirname(__file__), 'logs', 'app.log')
    if not os.path.exists(log_path):
        return ("Brak logu", 404)
    return send_file(log_path, as_attachment=True)

@app.route('/zamknij_zmiane', methods=['POST'])
@roles_required('lider', 'admin')
def zamknij_zmiane():
    from generator_raportow import generuj_excel_zmiany, otworz_outlook_z_raportem
    import os

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Zamykamy zlecenia
    cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
    uwagi = request.form.get('uwagi_lidera', '')
    cursor.execute("INSERT INTO raporty_koncowe (data_raportu, lider_uwagi) VALUES (%s, %s)", (date.today(), uwagi))
    conn.commit()
    conn.close()
    
    # 2. Generujemy raporty (Excel + notatka)
    try:
        xls_path, txt_path, pdf_path = generuj_excel_zmiany(date.today())
    except Exception:
        xls_path = None
        txt_path = None
        pdf_path = None

    # 3. Spróbuj otworzyć Outlooka (jeśli dostępny) — nie przerywamy w przeciwnym wypadku
    try:
        if xls_path:
            otworz_outlook_z_raportem(xls_path, uwagi)
    except Exception:
        app.logger.exception('Outlook open failed')

    # 4. Jeśli pliki wygenerowane, zwracamy ZIP do pobrania (automatyczne pobranie plików przez przeglądarkę)
    if xls_path or txt_path or ('pdf_path' in locals() and pdf_path):
        from zipfile import ZipFile
        zip_name = f"Raport_{date.today()}.zip"
        zip_path = os.path.join('raporty', zip_name)
        try:
            with ZipFile(zip_path, 'w') as z:
                if xls_path and os.path.exists(xls_path):
                    z.write(xls_path, arcname=os.path.basename(xls_path))
                if txt_path and os.path.exists(txt_path):
                    z.write(txt_path, arcname=os.path.basename(txt_path))
                if 'pdf_path' in locals() and pdf_path and os.path.exists(pdf_path):
                    z.write(pdf_path, arcname=os.path.basename(pdf_path))
            return send_file(zip_path, as_attachment=True)
        except Exception:
            app.logger.exception('Failed to create/send zip')

    # Fallback: jeśli nic do pobrania, przekieruj na stronę logowania
    return redirect('/login')

@app.route('/wyslij_raport_email', methods=['POST'])
def wyslij_raport_email(): return redirect('/')

if __name__ == '__main__':
    # Log startup information including PID and port to help detect multiple instances
    try:
        import os as _os
        pid = _os.getpid()
    except Exception:
        pid = 'unknown'
    try:
        app.logger.info('Starting server (pid=%s) host=%s port=%s', pid, '0.0.0.0', 8082)
    except Exception:
        pass
    print("[OK] Serwer wystartował: http://YOUR_IP_ADDRESS:8082 (pid=%s)" % pid)
    serve(app, host='0.0.0.0', port=8082, threads=6)
