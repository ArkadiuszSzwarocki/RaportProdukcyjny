from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash, jsonify
import logging
import os
import threading
import time
from waitress import serve
from datetime import date, datetime, timedelta
import json
from collections import defaultdict

from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import db
from db import get_db_connection
from dto.paleta import PaletaDTO
from routes_api import dodaj_plan_zaawansowany, dodaj_plan, usun_plan
from decorators import login_required, zarzad_required, roles_required
from utils.queries import QueryHelper
from core.error_handlers import setup_logging, register_error_handlers
from core.factory import create_app
from core.factory import create_app

# Create and configure Flask application
app = create_app()

# Ensure we always resolve DB connection at call-time so tests can monkeypatch `db.get_db_connection`
def get_db_connection():
    return db.get_db_connection()


# Backwards-compatible aliases for forms that post to root paths (keep working without reloading pages)
@app.route('/dodaj_plan_zaawansowany', methods=['POST'])
@login_required
def alias_dodaj_plan_zaawansowany():
    return dodaj_plan_zaawansowany()


@app.route('/dodaj_plan', methods=['POST'])
@login_required
def alias_dodaj_plan():
    return dodaj_plan()


@app.route('/usun_plan/<int:id>', methods=['POST'])
@login_required
def alias_usun_plan(id):
    return usun_plan(id)


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
        static_folder = app.static_folder or os.path.join(app.root_path, 'static')
        # Try common favicon files in order. Fall back to the bundled PNG logo.
        for fname in ('favicon.ico', 'favicon.svg', 'agro_logo.png'):
            path = os.path.join(static_folder, fname)
            if os.path.exists(path):
                try:
                    from flask import send_from_directory
                    return send_from_directory(static_folder, fname)
                except Exception:
                    return redirect(url_for('static', filename=fname))
        return ('', 204)
    except Exception:
        return ('', 204)


# Some devtools/extensions request a well-known file which we don't serve;
# respond with 204 No Content to avoid noisy 404/500 traces in logs.
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def _well_known_devtools():
    return ('', 204)

# Generic handler for any /.well-known probes to reduce noisy 404s
@app.route('/.well-known/<path:subpath>')
def _well_known_generic(subpath):
    return ('', 204)


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


@app.route('/debug/modal-move', methods=['POST'])
def debug_modal_move():
    try:
        data = request.get_json(force=True)
        # Log as info; JSON-encode to keep single-line entries
        try:
            app.logger.info('Modal-move debug: %s', json.dumps(data, ensure_ascii=False))
        except Exception:
            app.logger.info('Modal-move debug: %s', str(data))
    except Exception as e:
        try:
            app.logger.exception('Failed to record modal-move debug: %s', e)
        except Exception:
            pass
    return ('', 204)


# --- Test routes for slide/modal UI (development only) ---------------------------------
@app.route('/test/slide_test')
def slide_test():
    return render_template('slide_test.html')


@app.route('/_test/slide/<name>', methods=['GET'])
def _test_slide(name):
    # Return small HTML fragments used to demonstrate slide-over behavior
    if name == 'form':
        return """
            <form action="/_test/slide/submit" method="post">
                <div class="p-10">
                    <label>Wartość: <input name="val"/></label>
                    <button type="submit" class="btn">Zapisz</button>
                </div>
            </form>
        """
    if name == 'confirm':
        return """
            <div class="p-10">
                <h3>Potwierdź</h3>
                <p>Czy chcesz wykonać akcję testową?</p>
                <form method="post" action="/_test/slide/confirm_do">
                    <button class="btn" type="submit">Tak</button>
                </form>
            </div>
        """
    if name == 'large':
        longp = ' '.join(['Przykładowy tekst.'] * 80)
        return f"<div class='p-20'><h2>Duża treść testowa</h2><p>{longp}</p></div>"
    return f"<div class='p-10'>Treść testowa: {name}</div>"


@app.route('/_test/center/<name>', methods=['GET'])
def _test_center(name):
    if name == 'notice':
        return "<div class='p-10'><h3>Powiadomienie</h3><p>To jest center modal testowy.</p></div>"
    if name == 'form':
        return """
            <form action="/_test/center/submit" method="post">
                <div class="p-10">
                    <label>Imię: <input name="imie"/></label>
                    <button class="btn" type="submit">Wyślij</button>
                </div>
            </form>
        """
    return f"<div class='p-10'>Center test: {name}</div>"


@app.route('/_test/slide/submit', methods=['POST'])
def _test_slide_submit():
    # Simulate successful AJAX response (JSON)
    return ('{"success": true, "message": "Zapisano (test)"}', 200, {'Content-Type': 'application/json'})


@app.route('/_test/slide/confirm_do', methods=['POST'])
def _test_slide_confirm_do():
    return ('{"success": true, "message": "Potwierdzono (test)"}', 200, {'Content-Type': 'application/json'})


@app.route('/_test/center/submit', methods=['POST'])
def _test_center_submit():
    return ('{"success": true, "message": "Center: wyslano (test)"}', 200, {'Content-Type': 'application/json'})



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
        # Validate required form fields via central helper
        try:
            from utils.validation import require_field
            login_field = require_field(request.form, 'login')
            password_field = require_field(request.form, 'haslo')
        except Exception as e:
            flash(str(e), 'danger')
            return redirect('/login')

        conn = get_db_connection()
        cursor = conn.cursor()
        # Pobierz opcjonalne pole pracownik_id by mapować konto na rekord pracownika
        cursor.execute("SELECT id, haslo, rola, COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login = %s", (login_field,))
        row = cursor.fetchone()
        conn.close()
        if row:
            uid, hashed, rola, pracownik_id = row[0], row[1], row[2], row[3]
            if hashed and check_password_hash(hashed, password_field):
                session['zalogowany'] = True
                # Normalize role to lowercase to avoid case-sensitivity issues in templates
                session['rola'] = (rola or '').lower()
                # Zapisz login i powiązanie pracownika w sesji (może być None)
                session['login'] = login_field
                session['pracownik_id'] = int(pracownik_id) if pracownik_id is not None else None
                
                # Log login with current process PID
                app.logger.info(f"[LOGIN] User '{login_field}' logged in successfully (PID: {os.getpid()})")
                
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
                session['imie_nazwisko'] = imie_nazwisko or login_field
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
    # If no sekcja param, default to 'Dashboard' (center view for lider)
    # If sekcja param provided, use that specific section
    aktywna_sekcja = request.args.get('sekcja', 'Dashboard')
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
    
    # Use QueryHelper for database queries
    wszyscy = QueryHelper.get_pracownicy()
    zajeci_ids = [r[0] for r in QueryHelper.get_obsada_zmiany(dzisiaj)]
    dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
    obecna_obsada = QueryHelper.get_obsada_zmiany(dzisiaj, aktywna_sekcja)
    wpisy = QueryHelper.get_dziennik_zmiany(dzisiaj, aktywna_sekcja)
    
    # Format czas_start/czas_stop as HH:MM strings for templates
    for w in wpisy:
        try:
            w[3] = w[3].strftime('%H:%M') if w[3] else ''
        except Exception:
            w[3] = str(w[3]) if w[3] else ''
        try:
            w[4] = w[4].strftime('%H:%M') if w[4] else ''
        except Exception:
            w[4] = str(w[4]) if w[4] else ''
    
    plan_dnia = []
    palety_mapa = {}
    magazyn_palety = []
    unconfirmed_palety = []
    suma_plan = 0
    suma_wykonanie = 0
    zasyp_rozpoczete = QueryHelper.get_zasyp_started_produkty(dzisiaj)
    
    if aktywna_sekcja == 'Magazyn':
        # Zwracamy kolumny w porządku zgodnym z PaletaDTO.from_db_row fallback:
        raw_mag = QueryHelper.get_paletki_magazyn(dzisiaj)
        magazyn_palety = []
        for r in raw_mag:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            # Get czas_rzeczywistego_potwierdzenia (real confirmation time in HH:MM format)
            czas_rzeczywisty = '-'
            try:
                # Try to get from raw row at index 10 (NEW column with actual confirmation time)
                if len(r) > 10 and r[10]:
                    czas_obj = r[10]
                    if hasattr(czas_obj, 'strftime'):
                        czas_rzeczywisty = czas_obj.strftime('%H:%M')
                    else:
                        # Might be string like '08:43:21'
                        czas_str = str(czas_obj)
                        if ':' in czas_str:
                            parts = czas_str.split(':')
                            czas_rzeczywisty = f"{parts[0]}:{parts[1]}"  # HH:MM only
                else:
                    # Fallback: if czas_rzeczywistego_potwierdzenia is NULL, calculate it from data_dodania + 2 min
                    if dt and hasattr(dt, 'strftime'):
                        from datetime import timedelta
                        czas_oblic = dt + timedelta(minutes=2)
                        czas_rzeczywisty = czas_oblic.strftime('%H:%M')
            except Exception:
                pass
            # include formatted czas_rzeczywistego_potwierdzenia for display
            magazyn_palety.append((dto.produkt, dto.waga, sdt, dto.id, dto.plan_id, dto.status, czas_rzeczywisty))
        
        # Oblicz suma_wykonanie z wszystkich palet w magazynie
        suma_wykonanie = sum(p[1] for p in magazyn_palety)
        
        # Pobierz niepotwierdzone palety (status != 'przyjeta'), by powiadomić magazyn jeśli nie potwierdzi w ciągu 10 minut
        try:
            raw = QueryHelper.get_unconfirmed_paletki(dzisiaj)
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
                    seq = QueryHelper.get_paleta_seq_number(plan_id, pid)
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

    plan_dnia = QueryHelper.get_plan_produkcji(dzisiaj, aktywna_sekcja if aktywna_sekcja != 'Dashboard' else 'Workowanie')
    
    # Dla Workowania: fallback - pobierz plany Workowania (bufor) które są zaplanowane lub w toku
    if aktywna_sekcja == 'Workowanie' and not plan_dnia:
        # Workowanie shows Workowanie plans (buffer) - NOT Zasyp!
        try:
            conn_work = get_db_connection()
            cursor_work = conn_work.cursor()
            cursor_work.execute(
                "SELECT id, produkt, tonaz, status, real_start, real_stop, "
                "TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, "
                "typ_produkcji, wyjasnienie_rozbieznosci "
                "FROM plan_produkcji "
                "WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie' AND status IN ('w toku', 'zaplanowane') "
                "ORDER BY CASE status WHEN 'w toku' THEN 1 ELSE 2 END, kolejnosc ASC, id ASC",
                (dzisiaj,)
            )
            plan_dnia = [list(r) for r in cursor_work.fetchall()]
            cursor_work.close()
            conn_work.close()
        except Exception:
            plan_dnia = []
    
    # Store raw datetime before formatting (needed for szarża time calculations)
    plan_start_times = {}
    for p in plan_dnia:
        # If real_start is None, use data_planu as fallback
        start_time = p[4] if p[4] else p[3]  # p[4] = real_start, p[3] = data_planu
        plan_start_times[p[0]] = start_time
    
    # Inicjalizuj conn i cursor dla Zasypu i Workowania
    conn = None
    cursor = None
    if aktywna_sekcja in ('Zasyp', 'Workowanie'):
        conn = get_db_connection()
        cursor = conn.cursor()
    
    # Store raw datetime before formatting (needed for szarża time calculations)
    plan_start_times = {}
    for p in plan_dnia:
        plan_start_times[p[0]] = p[4]  # Store raw real_start datetime
    
    # Format real_start/real_stop as HH:MM strings for templates
    for p in plan_dnia:
        try:
            p[4] = p[4].strftime('%H:%M') if p[4] else ''
        except Exception:
            p[4] = str(p[4]) if p[4] else ''
        try:
            p[5] = p[5].strftime('%H:%M') if p[5] else ''
        except Exception:
            p[5] = str(p[5]) if p[5] else ''
    
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
            raw_pal = QueryHelper.get_paletki_for_product(dzisiaj, p[1], p[9])
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
            # NOTE: Don't add to suma_wykonanie here - it's already calculated at line 776 from all magazyn_palety
        elif aktywna_sekcja in ('Workowanie', 'Zasyp'):
            # ZASYP: Show szarża (plan.tonaz) - szarże z tabeli szarze
            # WORKOWANIE: Show paletki for this Workowanie plan (buffer)
            if aktywna_sekcja == 'Zasyp':
                # For Zasyp: pobierz szarże z tabeli szarze dla tego planu
                cursor.execute(
                    "SELECT id, waga, godzina, data_dodania, pracownik_id, status FROM szarze WHERE plan_id=%s ORDER BY data_dodania ASC",
                    (p[0],)
                )
                szarze = cursor.fetchall()
                palety = []
                prev_time = plan_start_times.get(p[0])  # Start with plan's real_start
                
                for idx, sz in enumerate(szarze):
                    szarza_id = sz[0]
                    waga = sz[1]
                    godzina = sz[2] if sz[2] else ''
                    data_dodania = sz[3]
                    
                    # Calculate elapsed time between szarże
                    try:
                        current_time = data_dodania if isinstance(data_dodania, datetime) else datetime.fromisoformat(str(data_dodania))
                    except Exception:
                        current_time = None
                    
                    # Extract godzina (HH:MM) from data_dodania for display
                    godzina_display = "-"
                    try:
                        if hasattr(current_time, 'strftime'):
                            godzina_display = current_time.strftime('%H:%M')
                        elif current_time:
                            godzina_display = datetime.fromisoformat(str(current_time)).strftime('%H:%M')
                    except Exception:
                        pass
                    
                    elapsed_str = "-"
                    if current_time and prev_time:
                        try:
                            diff = (current_time - prev_time).total_seconds() / 60  # minutes
                            # If difference is negative or zero, show as 0m (prevents negative times)
                            if diff < 0:
                                elapsed_str = "0m"
                            elif diff >= 60:
                                hours = int(diff // 60)
                                mins = int(diff % 60)
                                elapsed_str = f"{hours}h {mins}m"
                            else:
                                elapsed_str = f"{int(diff)}m"
                        except Exception:
                            elapsed_str = "-"
                    
                    prev_time = current_time
                    
                    # Format display: "13:20 (20m)"
                    time_display = f"{godzina_display} ({elapsed_str})" if elapsed_str != "-" else godzina_display
                    
                    # Format tuple: (waga, time_display, id, plan_id, typ, tara, waga_brutto, status, czas_potwierdzenia, data_pełna)
                    # Put empty string for typ and status (not shown in table for Zasyp)
                    palety.append((waga, time_display, szarza_id, p[0], '', 0, 0, '', '', str(data_dodania)))
                
                app.logger.info(f"[DEBUG] Zasyp plan {p[0]}: loaded {len(szarze)} szarż, formatted palety={palety}")
                palety_mapa[p[0]] = palety
                # Użyj sumy wagi szarż (z tabeli szarze). Jeśli brak szarż, użyj wartości z DB (p[7]).
                try:
                    suma_szarz = sum(sz[1] for sz in szarze) if szarze else 0
                except Exception:
                    suma_szarz = 0
                # Jeśli są zarejestrowane szarże, pokaż ich sumę; w przeciwnym razie użyj tonaz_rzeczywisty z DB
                p[7] = suma_szarz if suma_szarz > 0 else (p[7] if p[7] else 0)
            else:
                # For Workowanie: show paletki (operatorzy dodają paletki)
                raw_pal = QueryHelper.get_paletki_for_plan(p[0])
                app.logger.info(f"[WORKOWANIE] Plan {p[0]}: get_paletki_for_plan returned {len(raw_pal)} paletki")
                if raw_pal and len(raw_pal) > 0:
                    app.logger.info(f"[WORKOWANIE] First paletka raw data: {raw_pal[0]}")
                palety = []
                prev_time_work = plan_start_times.get(p[0])  # Start with plan's real_start
                app.logger.info(f"[WORKOWANIE] Plan {p[0]}: plan_start_times value = {prev_time_work}, type = {type(prev_time_work)}")
                
                for r in raw_pal:
                    # SELECT returns: id, plan_id, waga, tara, waga_brutto, data_dodania, produkt, typ_produkcji, status, czas_potwierdzenia_s
                    # Indices:        0   1        2     3    4            5             6        7              8       9
                    waga = r[2]
                    data_dodania = r[5]
                    paleta_id = r[0]
                    typ_produkcji = r[7]
                    status = r[8] if r[8] else ''
                    tara = r[3]
                    waga_brutto = r[4]
                    
                    # Format time
                    try:
                        sdt = data_dodania.strftime('%H:%M') if hasattr(data_dodania, 'strftime') else str(data_dodania)
                        sdt_full = data_dodania.strftime('%Y-%m-%d %H:%M:%S') if hasattr(data_dodania, 'strftime') else str(data_dodania)
                    except Exception:
                        sdt = ''
                        sdt_full = ''
                    
                    # Calculate elapsed time from previous paletka
                    try:
                        current_time = data_dodania if isinstance(data_dodania, datetime) else datetime.fromisoformat(str(data_dodania))
                    except Exception:
                        current_time = None
                    
                    elapsed_str = "-"
                    if current_time and prev_time_work:
                        try:
                            diff = (current_time - prev_time_work).total_seconds() / 60  # minutes
                            # If difference is negative or zero, show as 0m (prevents negative times)
                            if diff < 0:
                                elapsed_str = "0m"
                            elif diff >= 60:
                                hours = int(diff // 60)
                                mins = int(diff % 60)
                                elapsed_str = f"{hours}h {mins}m"
                            else:
                                elapsed_str = f"{int(diff)}m"
                        except Exception:
                            elapsed_str = "-"
                    
                    prev_time_work = current_time
                    
                    # Format display: "13:20 (20m)"
                    time_display = f"{sdt} ({elapsed_str})" if elapsed_str != "-" else sdt
                    app.logger.info(f"[WORKOWANIE] Paletka {paleta_id}: time_display = '{time_display}' (sdt='{sdt}', elapsed_str='{elapsed_str}')")
                    
                    # Format elapsed time from confirmation
                    czas_potwierdzenia_s = r[9]
                    cps = None
                    try:
                        if czas_potwierdzenia_s is not None:
                            secs = int(czas_potwierdzenia_s)
                            if secs >= 3600:
                                cps = f"{secs//3600}h {(secs%3600)//60:02d}m"
                            elif secs >= 60:
                                cps = f"{secs//60}m {secs%60:02d}s"
                            else:
                                cps = f"{secs}s"
                        else:
                            cps = ''
                    except Exception:
                        cps = ''
                    
                    # Create tuple matching Zasyp format: (waga, time_display, id, plan_id, typ, tara, waga_brutto, status, elapsed, data_full)
                    palety.append((waga, time_display, paleta_id, p[0], typ_produkcji, tara, waga_brutto, status, cps, sdt_full))
                app.logger.info(f"[WORKOWANIE] Plan {p[0]}: created {len(palety)} formatted tuples")
                if palety and len(palety) > 0:
                    app.logger.info(f"[WORKOWANIE] First formatted tuple: {palety[0]}")
                palety_mapa[p[0]] = palety
                # Save original tonaz_rzeczywisty (pula) before overwriting p[7]
                tonaz_rzeczywisty_pula = p[7]  # This is the available amount to pack
                # Update p[7] with tonaz_rzeczywisty (sum of paletki weights)
                waga_kg = sum(pal[0] for pal in palety)
                p[7] = waga_kg  # What operator packed (sum of paletki)
                # Append pula at end for template to access
                p.append(tonaz_rzeczywisty_pula)  # p[11] = pula do spakowania (tonaz_rzeczywisty)
                # For Workowanie, ALWAYS add to suma_wykonanie regardless of is_quality
                # (quality checks are for plan counts, not actual execution weights)
                suma_wykonanie += waga_kg

        waga_workowania = 0
        diff = 0
        alert = False
        if aktywna_sekcja == 'Zasyp':
            # Na Zasypie: p[7] już zawiera tonaz_rzeczywisty (akumulacja +SZARŻA)
            # To jest WYKONANIE dla tej konkretnej szarży, nie trzeba liczyć z Workowania
            waga_workowania = p[7]  # To już jest wykonanie
            
            if p[2]:  # p[2] = plan (tonaz)
                diff = p[2] - waga_workowania
                if abs(diff) > 10: alert = True # Tolerancja 10kg
            # For dashboard totals when viewing Zasyp, use wykonanie (tonaz_rzeczywisty) z szarży
            if not is_quality:
                suma_wykonanie += (waga_workowania if waga_workowania else 0)
        p.extend([waga_workowania, diff, alert])

    # Zamknij cursor i connection na koniec pętli
    if cursor:
        cursor.close()
    if conn:
        conn.close()

    next_workowanie_id = None
    if aktywna_sekcja == 'Workowanie':
        kandydaci = [p for p in plan_dnia if p[3] == 'zaplanowane']
        kandydaci.sort(key=lambda x: x[0])
        if kandydaci: next_workowanie_id = kandydaci[0][0]

    # Build a map product -> buffer plan id (first open Workowanie plan for that product)
    buffer_map = {}
    try:
        plans_work = plans_workowanie if 'plans_workowanie' in locals() else []
        for p in plans_work:
            try:
                prod = p[1]
                status = p[3]
                pid = p[0]
                if status == 'w toku' and prod and prod not in buffer_map:
                    buffer_map[prod] = pid
            except Exception:
                continue
    except Exception:
        buffer_map = {}

    # Pobierz rekordy obecności dla bieżącego dnia
    raporty_hr = QueryHelper.get_presence_records_for_day(dzisiaj)

    # Przygotuj listę pracowników dostępnych do nadgodzin: wyklucz tych, którzy mają wpis w obecnosc
    try:
        ob = QueryHelper.get_absence_ids_for_day(dzisiaj)
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
    quality_count = QueryHelper.get_pending_quality_count()

    # If user is leader/admin, fetch recent pending leave requests for dashboard
    wnioski_pending = []
    try:
        if role in ['lider', 'admin']:
            wnioski_pending = QueryHelper.get_pending_leave_requests(limit=50)
    except Exception:
        try:
            app.logger.exception('Failed to fetch pending wnioski for dashboard')
        except Exception:
            pass

    # Pobierz planowane urlopy (następne 60 dni)
    planned_leaves = QueryHelper.get_planned_leaves(days_ahead=60, limit=500)

    # Pobierz ostatnie nieobecności (ostatnie 30 dni)
    recent_absences = QueryHelper.get_recent_absences(days_back=30, limit=500)

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

    try:
        app.logger.info('Rendering index: sekcja=%s plans=%d palety_map_keys=%d unconfirmed_palety=%d open_stop=%s shift_notes_count=%d', aktywna_sekcja, len(plan_dnia) if plan_dnia is not None else 0, len(palety_mapa.keys()) if isinstance(palety_mapa, dict) else 0, len(unconfirmed_palety) if hasattr(unconfirmed_palety, '__len__') else 0, request.args.get('open_stop'), len(shift_notes) if shift_notes else 0)
    except Exception:
        app.logger.exception('Error logging index render info')

    # --- Dashboard overview: load full plans for Zasyp and Workowanie for the global dashboard ---
    plans_zasyp = []
    plans_workowanie = []
    try:
        conn2 = get_db_connection()
        cursor2 = conn2.cursor()
        for sek in ('Zasyp', 'Workowanie'):
            cursor2.execute("SELECT id, produkt, tonaz, status, real_start, real_stop, TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci, uszkodzone_worki FROM plan_produkcji WHERE DATE(data_planu) = %s AND sekcja = %s AND status != 'nieoplacone' AND is_deleted = 0 ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, kolejnosc ASC, id ASC", (dzisiaj, sek))
            rows = [list(r) for r in cursor2.fetchall()]
            # format times and ensure numeric defaults similar to main flow
            for p in rows:
                try:
                    p[4] = p[4].strftime('%H:%M') if p[4] else ''
                except Exception:
                    p[4] = str(p[4]) if p[4] else ''
                try:
                    p[5] = p[5].strftime('%H:%M') if p[5] else ''
                except Exception:
                    p[5] = str(p[5]) if p[5] else ''
                if p[7] is None:
                    p[7] = 0
            if sek == 'Zasyp':
                app.logger.info('DEBUG: fetched raw plans_zasyp rows count=%d', len(rows) if rows else 0)
                try:
                    # Log a concise representation of rows for debugging UI mismatch
                    app.logger.debug('DEBUG: plans_zasyp rows: %s', rows)
                except Exception:
                    app.logger.exception('Failed to log plans_zasyp rows')
                # Fix realization (p[7]) for Zasyp plans: compute from sum of szarze
                try:
                    conn_szarze = get_db_connection()
                    cursor_szarze = conn_szarze.cursor()
                    for p in rows:
                        plan_id = p[0]
                        cursor_szarze.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
                        result = cursor_szarze.fetchone()
                        suma_szarz = result[0] if result and result[0] is not None else 0
                        # Use sum of actual szarze if > 0, otherwise fallback to DB tonaz_rzeczywisty
                        p[7] = suma_szarz if suma_szarz > 0 else (p[7] if p[7] else 0)
                    cursor_szarze.close()
                    conn_szarze.close()
                except Exception:
                    app.logger.exception('Error computing szarze sums for Zasyp dashboard')
                plans_zasyp = rows
            else:
                plans_workowanie = rows
        try:
            cursor2.close()
            conn2.close()
        except Exception:
            pass
    except Exception:
        try:
            app.logger.exception('Failed to load plans for dashboard overview')
        except Exception:
            pass

    # If explicit sekcja query param provided, render the original production dashboard view
    # so links like ?sekcja=Zasyp / Workowanie / Magazyn behave as before.
    try:
        plan_data = plan_dnia
        palety_mapa_local = palety_mapa
        
        if 'sekcja' in request.args:
            # For Zasyp/Workowanie sections, use the fresh plans_zasyp/plans_workowanie data
            if aktywna_sekcja == 'Zasyp':
                plan_data = plans_zasyp
            elif aktywna_sekcja == 'Workowanie':
                # Ensure palety sums are computed for Workowanie plans so 'Realizacja' shows produced palety
                palety_mapa_local = {}
                try:
                    for p in plans_workowanie:
                        raw_pal = QueryHelper.get_paletki_for_plan(p[0])
                        palety = []
                        for r in raw_pal:
                            # SELECT returns: id, plan_id, waga, tara, waga_brutto, data_dodania, produkt, typ_produkcji, status, czas_potwierdzenia_s
                            # Indices:        0   1        2     3    4            5             6        7              8       9
                            waga = r[2]
                            data_dodania = r[5]
                            paleta_id = r[0]
                            typ_produkcji = r[7]
                            status = r[8] if r[8] else ''
                            tara = r[3]
                            waga_brutto = r[4]
                            
                            # Format time
                            try:
                                sdt = data_dodania.strftime('%H:%M') if hasattr(data_dodania, 'strftime') else str(data_dodania)
                                sdt_full = data_dodania.strftime('%Y-%m-%d %H:%M:%S') if hasattr(data_dodania, 'strftime') else str(data_dodania)
                            except Exception:
                                sdt = ''
                                sdt_full = ''
                            
                            # Format elapsed time
                            czas_potwierdzenia_s = r[9]
                            cps = None
                            try:
                                if czas_potwierdzenia_s is not None:
                                    secs = int(czas_potwierdzenia_s)
                                    if secs >= 3600:
                                        cps = f"{secs//3600}h {(secs%3600)//60:02d}m"
                                    elif secs >= 60:
                                        cps = f"{secs//60}m {secs%60:02d}s"
                                    else:
                                        cps = f"{secs}s"
                                else:
                                    cps = ''
                            except Exception:
                                cps = ''
                            
                            # Create tuple matching Zasyp format
                            palety.append((waga, sdt, paleta_id, p[0], typ_produkcji, tara, waga_brutto, status, cps, sdt_full))
                        
                        palety_mapa_local[p[0]] = palety
                        # sum weights
                        try:
                            p[7] = sum([float(pal[0]) for pal in palety]) if palety else 0
                        except Exception:
                            p[7] = 0
                except Exception:
                    palety_mapa_local = {}
                plan_data = plans_workowanie
        
        # Zamknij connection dla Zasypu
        if conn:
            conn.close()
        
        # Sprawdź czy są zlecenia 'wstrzymane' z wczoraj dla każdej sekcji
        has_suspended_yesterday = False
        try:
            if aktywna_sekcja in ('Zasyp', 'Workowanie'):
                wczoraj = (datetime.now().date() - timedelta(days=1)).strftime('%Y-%m-%d')
                conn_check = get_db_connection()
                cursor_check = conn_check.cursor()
                cursor_check.execute(
                    "SELECT COUNT(*) FROM plan_produkcji WHERE DATE(data_planu) = %s AND sekcja = %s AND status = 'wstrzymane'",
                    (wczoraj, aktywna_sekcja)
                )
                result = cursor_check.fetchone()
                has_suspended_yesterday = result[0] > 0 if result else False
                cursor_check.close()
                conn_check.close()
        except Exception as e:
            app.logger.exception('Error checking for suspended orders from yesterday: %s', str(e))
            has_suspended_yesterday = False
        
        # If sekcja='Dashboard' (no param), render the global dashboard center (with Zasyp + Workowanie)
        # Otherwise render the production section dashboard
        if aktywna_sekcja == 'Dashboard':
            return render_template('dashboard_global.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada, wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety, unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr, zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id, now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count, wnioski_pending=wnioski_pending, planned_leaves=planned_leaves, recent_absences=recent_absences, shift_notes=shift_notes, plans_zasyp=plans_zasyp, plans_workowanie=plans_workowanie, buffer_map=buffer_map)
        else:
            return render_template('dashboard.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada, wpisy=wpisy, plan=plan_data, palety_mapa=palety_mapa_local, magazyn_palety=magazyn_palety, unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr, zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id, now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count, wnioski_pending=wnioski_pending, has_suspended_yesterday=has_suspended_yesterday, buffer_map=buffer_map)
    except Exception:
        # Zamknij connection w przypadku błędu
        if conn:
            conn.close()
        app.logger.exception('Failed rendering production dashboard, falling back to global')
        # Fallback: always render dashboard_global to ensure consistent fallback
        return render_template('dashboard_global.html', sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy, hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada, wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety, unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie, rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr, zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id, now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count, wnioski_pending=wnioski_pending, planned_leaves=planned_leaves, recent_absences=recent_absences, shift_notes=shift_notes, plans_zasyp=plans_zasyp, plans_workowanie=plans_workowanie, buffer_map=buffer_map)


@app.route('/panel_wnioski_page', methods=['GET'])
@roles_required('lider', 'admin')
def panel_wnioski_page():
    # pełnostronicowy widok zatwierdzeń wniosków
    wnioski = []
    try:
        raw_wnioski = QueryHelper.get_pending_leave_requests(limit=200)
        wnioski = raw_wnioski
    except Exception:
        app.logger.exception('Failed loading wnioski for full page')
    return render_template('panels_full/wnioski_full.html', wnioski=wnioski)


@app.route('/panel/planowane')
@login_required
def panel_planowane_page():
    planned = []
    try:
        planned = QueryHelper.get_planned_leaves(days_ahead=60, limit=500)
    except Exception:
        app.logger.exception('Failed loading planned leaves for full page')
    return render_template('panels_full/planowane_full.html', planned_leaves=planned)


@app.route('/panel/obecnosci')
@login_required
def panel_obecnosci_page():
    recent = []
    try:
        raw_recent = QueryHelper.get_recent_absences(days_back=30, limit=500)
        # Convert keys to match template: data_wpisu -> data, ilosc_godzin -> godziny
        recent = [{'id': r['id'], 'pracownik': r['pracownik'], 'typ': r['typ'], 'data': r['data_wpisu'], 'godziny': r['ilosc_godzin'], 'komentarz': r['komentarz']} for r in raw_recent]
    except Exception:
        app.logger.exception('Failed loading absences for full page')
    return render_template('panels_full/obecnosci_full.html', recent_absences=recent)


@app.route('/panel/obsada')
@login_required
def panel_obsada_page():
    # Render full page but embed obsada fragment server-side (avoid iframe and nested layout)
    sekcja = request.args.get('sekcja', 'Workowanie')
    date_str = request.args.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()

    obsady_map = {}
    wszyscy = []
    try:
        obsady_map = QueryHelper.get_obsada_for_date(qdate)
        wszyscy = QueryHelper.get_unassigned_pracownicy(qdate)
    except Exception:
        app.logger.exception('Failed loading obsada for panel page')

    return render_template('panels_full/obsada_full.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'))


@app.route('/test-download')
@login_required
def test_download():
    """Strona testowa do pobrania raportów"""
    return render_template('test_download.html')


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
@roles_required('admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laboratorium')
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
                pracownik_id,
                data_zakonczenia
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
            # Formatuj czas_start / czas_stop jako HH:MM (bez błędnego zakładania timedelta)
            def _fmt_time_field(val):
                # Accept datetime-like or string values; return zero-padded HH:MM or HH:MM:SS
                try:
                    if hasattr(val, 'strftime'):
                        return val.strftime('%H:%M')
                    if isinstance(val, (int, float)):
                        # unlikely, but handle seconds-since-midnight
                        h = int(val) // 3600
                        m = (int(val) % 3600) // 60
                        return f"{h:02d}:{m:02d}"
                    s = str(val).strip()
                    if not s:
                        return '??:??'
                    # Normalize common formats like H:MM:SS or HH:MM:SS or HH:MM
                    parts = s.split(':')
                    if len(parts) == 3:
                        h = int(parts[0])
                        mm = int(parts[1])
                        ss = int(parts[2])
                        return f"{h:02d}:{mm:02d}:{ss:02d}"
                    if len(parts) == 2:
                        h = int(parts[0])
                        mm = int(parts[1])
                        return f"{h:02d}:{mm:02d}"
                    # fallback
                    return s
                except Exception:
                    try:
                        return str(val)
                    except Exception:
                        return '??:??'

            awaria['czas_start_str'] = _fmt_time_field(awaria.get('czas_start'))
            awaria['czas_stop_str'] = _fmt_time_field(awaria.get('czas_stop'))
            
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
            app.logger.debug(f"DEBUG: Pobrano {len(awaria['komentarze'])} komentarzy dla awarii #{awaria['id']}")
            cursor_kom.close()
            conn_kom.close()
            
            # Pobierz historię zmian statusu
            conn_hist = get_db_connection()
            cursor_hist = conn_hist.cursor(dictionary=True)
            cursor_hist.execute("""
                SELECT dz.id, dz.stary_status, dz.nowy_status, p.imie_nazwisko, dz.data_zmiany
                FROM dziennik_zmian_statusu dz
                LEFT JOIN pracownicy p ON dz.zmieniony_przez = p.id
                WHERE dz.awaria_id = %s
                ORDER BY dz.data_zmiany DESC
            """, (awaria['id'],))
            awaria['historia_statusu'] = cursor_hist.fetchall()
            cursor_hist.close()
            conn_hist.close()
        
        return render_template('dur_awarie.html', awarie=awarie)
    except Exception as e:
        app.logger.exception(f'Error in dur_awarie: {e}')
        flash('⚠️ Błąd przy wczytywaniu awarii', 'error')
        return redirect('/')


@app.route('/api/dur/zmien_status/<int:awaria_id>', methods=['POST'])
@roles_required('dur', 'admin', 'zarzad')
def dur_zmien_status(awaria_id):
    """Zmień status awarii i zaloguj zmianę jako komentarz"""
    try:
        nowy_status = request.form.get('status', '').strip()
        if not nowy_status:
            return jsonify({'success': False, 'message': 'Status nie może być pusty'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz obecny status
        cursor.execute("SELECT status FROM dziennik_zmiany WHERE id = %s", (awaria_id,))
        awaria = cursor.fetchone()
        if not awaria:
            conn.close()
            return jsonify({'success': False, 'message': 'Awaria nie znaleziona'}), 404
        
        stary_status = awaria.get('status')
        
        # Zaktualizuj status
        cursor.execute("UPDATE dziennik_zmiany SET status = %s WHERE id = %s", (nowy_status, awaria_id))
        
        # Zaloguj zmianę jako komentarz
        pracownik_id = session.get('pracownik_id')
        status_msg = f"🔄 Status zmieniony: {stary_status} → {nowy_status} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        cursor.execute(
            "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
            (awaria_id, pracownik_id, status_msg)
        )
        
        # Zaloguj również w dziennik_zmian_statusu (dla historii)
        cursor.execute("""
            INSERT INTO dziennik_zmian_statusu (awaria_id, stary_status, nowy_status, zmieniony_przez, data_zmiany)
            VALUES (%s, %s, %s, %s, NOW())
        """, (awaria_id, stary_status, nowy_status, pracownik_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Status zmieniony na "{nowy_status}"',
            'old_status': stary_status,
            'new_status': nowy_status
        }), 200
    except Exception as e:
        app.logger.exception(f'Error in dur_zmien_status: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@app.route('/api/dur/zatwierdz_awarię/<int:awaria_id>', methods=['POST'])
@login_required
def dur_zatwierdz_awarię(awaria_id):
    """Zatwierdź awarie - zmień status i dodaj komentarz"""
    try:
        rola = session.get('rola')
        pracownik_id = session.get('pracownik_id')
        app.logger.info(f"=== dur_zatwierdz_awarię START ===")
        app.logger.info(f"  awaria_id={awaria_id}, rola={rola}, pracownik_id={pracownik_id}")
        
        status = request.form.get('status', '').strip()
        komentarz = request.form.get('komentarz', '').strip()
        
        app.logger.info(f"  Form data: status='{status}' (len={len(status)}), komentarz='{komentarz}' (len={len(komentarz)})")
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz obecny status przed zmianą
        cursor.execute("SELECT status FROM dziennik_zmiany WHERE id = %s", (awaria_id,))
        awaria_przed = cursor.fetchone()
        
        # Jeśli awaria nie istnieje - zwróć błąd
        if not awaria_przed:
            app.logger.warning(f"DEBUG: Awaria #{awaria_id} nie znaleziona w database")
            return jsonify({'success': False, 'message': 'Awaria nie znaleziona'}), 404
        
        stary_status = awaria_przed.get('status')
        app.logger.info(f"  stary_status='{stary_status}'")
        
        # Aktualizuj status
        status_zmieniony = False
        if status and stary_status != status:
            app.logger.info(f"  ✓ Status się zmienił: '{stary_status}' → '{status}'")
            cursor.execute("UPDATE dziennik_zmiany SET status = %s WHERE id = %s", (status, awaria_id))
            conn.commit()
            status_zmieniony = True
            
            # Jeśli status = 'zakończone', ustaw data_zakonczenia na dzisiaj
            if status == 'zakończone':
                cursor.execute("UPDATE dziennik_zmiany SET data_zakonczenia = %s WHERE id = %s", (date.today(), awaria_id))
                conn.commit()
        else:
            app.logger.info(f"  ✗ Status nie zmienił się: status='{status}', stary_status='{stary_status}'")
        
        # Dodaj automatyczny komentarz jeśli zmienił się status
        if status_zmieniony:
            status_msg = f"🔄 Status: {stary_status} → {status} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            app.logger.info(f"DEBUG: Dodawanie auto-komentarza dla awarii #{awaria_id}: {status_msg}")
            
            cursor.execute(
                "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
                (awaria_id, pracownik_id, status_msg)
            )
            conn.commit()
            app.logger.info(f"DEBUG: Auto-komentarz dodany i zacommit'owany")
        
        # Dodaj komentarz użytkownika jeśli jest wpisany
        if komentarz:
            app.logger.info(f"DEBUG: Dodawanie ręcznego komentarza dla awarii #{awaria_id}: {komentarz}")
            cursor.execute(
                "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
                (awaria_id, pracownik_id, komentarz)
            )
            conn.commit()
            app.logger.info(f"DEBUG: Ręczny komentarz dodany i zacommit'owany")
        
        cursor.close()
        conn.close()
        
        msg = f'✓ Awaria #{awaria_id} zaktualizowana'
        if status_zmieniony:
            msg += f' (status: {status})'
        if komentarz:
            msg += ' (komentarz dodany)'
        
        # Zwróć JSON zamiast redirect, aby formularz mógł być AJAX
        return jsonify({'success': True, 'message': msg}), 200
    except Exception as e:
        app.logger.exception(f'Error in dur_zatwierdz_awarię: {e}')
        return jsonify({'success': False, 'message': f'⚠️ Błąd: {str(e)}'}), 500



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
            SELECT id, produkt, data_planu, sekcja, tonaz, status, real_start, real_stop, tonaz_rzeczywisty
            FROM plan_produkcji
            WHERE COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc'
            ORDER BY data_planu DESC, id DESC
        """)
        zlecenia = [list(r) for r in cursor.fetchall()]
        # Format real_start/real_stop as HH:MM
        for z in zlecenia:
            try:
                z[6] = z[6].strftime('%H:%M') if z[6] else ''
            except Exception:
                z[6] = str(z[6]) if z[6] else ''
            try:
                z[7] = z[7].strftime('%H:%M') if z[7] else ''
            except Exception:
                z[7] = str(z[7]) if z[7] else ''
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
        typ = request.form.get('typ_produkcji') or 'worki_zgrzewane_25'

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

# Accept GET gracefully for probes; redirect to index instead of 405
@app.route('/zamknij_zmiane', methods=['GET'])
@roles_required('lider', 'admin')
def zamknij_zmiane_get():
    return redirect(url_for('index'))


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
