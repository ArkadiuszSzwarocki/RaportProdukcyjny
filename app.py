from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash, jsonify
import logging
import os
import threading
import time
from waitress import serve
from datetime import date, datetime, timedelta
import json
from collections import defaultdict
from zipfile import ZipFile

from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from app import db
from app.db import get_db_connection
from app.dto.paleta import PaletaDTO
from app.decorators import login_required, zarzad_required, roles_required
from app.utils.queries import QueryHelper
from app.core.error_handlers import setup_logging, register_error_handlers
from app.core.factory import create_app

try:
    from generator_raportow import generuj_excel_zmiany, otworz_outlook_z_raportem
except (ImportError, ModuleNotFoundError):
    generuj_excel_zmiany = None
    otworz_outlook_z_raportem = None

# Create and configure Flask application
app = create_app()

# Ensure we always resolve DB connection at call-time so tests can monkeypatch `db.get_db_connection`
def get_db_connection():
    return db.get_db_connection()


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
