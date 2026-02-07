"""Main application routes: dashboard index, shift closing, reports."""

from flask import Blueprint, render_template, request, redirect, url_for, session, send_file, jsonify
from datetime import date, datetime, timedelta
import json
import os
from app.decorators import login_required, roles_required
from app.db import get_db_connection
from app.dto.paleta import PaletaDTO
from app.utils.queries import QueryHelper

try:
    from generator_raportow import generuj_excel_zmiany, otworz_outlook_z_raportem
except (ImportError, ModuleNotFoundError):
    generuj_excel_zmiany = None
    otworz_outlook_z_raportem = None

main_bp = Blueprint('main', __name__)


@main_bp.route('/debug/modal-move', methods=['POST'])
def debug_modal_move():
    """Log modal-move debug data from client (AJAX).
    
    This endpoint accepts JSON payloads from the UI for debugging modal drag/drop behavior.
    """
    from flask import current_app
    app = current_app
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


@main_bp.route('/')
@login_required
def index():
    """Main dashboard: displays production plans, palety inventory, absence/leave management.
    
    Supports sections: Dashboard, Zasyp, Workowanie, Magazyn, and others.
    Dynamically loads data based on selected sekcja and date parameters.
    """
    from flask import current_app
    app = current_app
    
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

        waga_workowania = 0
        diff = 0
        alert = False
        if aktywna_sekcja == 'Zasyp':
            waga_workowania = p[7]
            if p[2]:  # p[2] = plan (tonaz)
                diff = p[2] - waga_workowania
                if abs(diff) > 10: alert = True # Tolerancja 10kg
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
    
    # Pobierz rekordy obecności dla bieżącego dnia
    raporty_hr = QueryHelper.get_presence_records_for_day(dzisiaj)

    # Przygotuj listę pracowników dostępnych do nadgodzin
    try:
        ob = QueryHelper.get_absence_ids_for_day(dzisiaj)
        ob_all_ids = set(r[0] for r in ob)
        ob_nonprivate_ids = set(r[0] for r in ob if str(r[1]).strip().lower() != 'wyjscie prywatne')
        hr_dostepni = [p for p in wszyscy if p[0] not in ob_nonprivate_ids]
        hr_pracownicy = [p for p in wszyscy if p[0] not in ob_all_ids and p[0] not in zajeci_ids]
    except Exception:
        try:
            hr_dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
            hr_pracownicy = [p for p in wszyscy if p[0] not in zajeci_ids]
        except Exception:
            hr_dostepni = wszyscy
            hr_pracownicy = wszyscy

    # Liczba zleceń jakościowych
    quality_count = QueryHelper.get_pending_quality_count()

    # If user is leader/admin, fetch recent pending leave requests for dashboard
    wnioski_pending = []
    try:
        if role in ['lider', 'admin']:
            wnioski_pending = QueryHelper.get_pending_leave_requests(limit=50)
    except Exception:
        pass

    # Pobierz planowane urlopy
    planned_leaves = QueryHelper.get_planned_leaves(days_ahead=60, limit=500)
    recent_absences = QueryHelper.get_recent_absences(days_back=30, limit=500)

    # Wczytaj notatki zmianowe
    shift_notes = []
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
            pass
        try:
            cursor_notes.execute("SELECT id, pracownik_id, DATE_FORMAT(date, '%Y-%m-%d'), note, author, created FROM shift_notes ORDER BY created DESC LIMIT 200")
            rows = cursor_notes.fetchall()
            for r in rows:
                shift_notes.append({'id': r[0], 'pracownik_id': r[1], 'date': r[2], 'note': r[3], 'author': r[4], 'created': r[5]})
        except Exception:
            shift_notes = []
        cursor_notes.close()
        conn_notes.close()
    except Exception:
        pass

    # Dashboard overview: load full plans for Zasyp and Workowanie
    plans_zasyp = []
    plans_workowanie = []
    try:
        conn2 = get_db_connection()
        cursor2 = conn2.cursor()
        for sek in ('Zasyp', 'Workowanie'):
            cursor2.execute("""SELECT id, produkt, tonaz, status, real_start, real_stop, TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci, uszkodzone_worki 
                            FROM plan_produkcji WHERE DATE(data_planu) = %s AND sekcja = %s AND status != 'nieoplacone' AND is_deleted = 0 
                            ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, kolejnosc ASC, id ASC""", (dzisiaj, sek))
            rows = [list(r) for r in cursor2.fetchall()]
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
                plans_zasyp = rows
            else:
                plans_workowanie = rows
        cursor2.close()
        conn2.close()
    except Exception:
        pass

    # Render appropriate template based on section
    try:
        if aktywna_sekcja == 'Dashboard':
            return render_template('dashboard_global.html', 
                sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy,
                hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada,
                wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety,
                unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie,
                rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr,
                zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id,
                now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count,
                wnioski_pending=wnioski_pending, planned_leaves=planned_leaves,
                recent_absences=recent_absences, shift_notes=shift_notes,
                plans_zasyp=plans_zasyp, plans_workowanie=plans_workowanie, buffer_map=buffer_map)
        else:
            return render_template('dashboard.html',
                sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy,
                hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada,
                wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety,
                unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie,
                rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr,
                zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id,
                now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count,
                wnioski_pending=wnioski_pending, buffer_map=buffer_map)
    except Exception:
        if conn:
            conn.close()
        return render_template('dashboard_global.html', 
            sekcja=aktywna_sekcja, pracownicy=dostepni, wszyscy_pracownicy=wszyscy,
            hr_pracownicy=hr_pracownicy, hr_dostepni=hr_dostepni, obsada=obecna_obsada,
            wpisy=wpisy, plan=plan_dnia, palety_mapa=palety_mapa, magazyn_palety=magazyn_palety,
            unconfirmed_palety=unconfirmed_palety, suma_plan=suma_plan, suma_wykonanie=suma_wykonanie,
            rola=session.get('rola'), dzisiaj=dzisiaj, raporty_hr=raporty_hr,
            zasyp_rozpoczete=zasyp_rozpoczete, next_workowanie_id=next_workowanie_id,
            now_time=datetime.now().strftime('%H:%M'), quality_count=quality_count,
            wnioski_pending=wnioski_pending, planned_leaves=planned_leaves,
            recent_absences=recent_absences, shift_notes=shift_notes,
            plans_zasyp=plans_zasyp, plans_workowanie=plans_workowanie, buffer_map=buffer_map)


@main_bp.route('/zamknij_zmiane', methods=['GET'])
@roles_required('lider', 'admin')
def zamknij_zmiane_get():
    """Redirect GET requests on shift close endpoint to index."""
    return redirect(url_for('main.index'))


@main_bp.route('/zamknij_zmiane', methods=['POST'])
@roles_required('lider', 'admin')
def zamknij_zmiane():
    """Close current shift (zmiana) and generate final reports.
    
    - Closes all 'w toku' (in progress) production plans
    - Generates Excel and text reports
    - Optionally sends report via Outlook if available
    - Returns ZIP file with generated reports for download
    """
    from flask import current_app
    app = current_app
    
    if generuj_excel_zmiany is None or otworz_outlook_z_raportem is None:
        return redirect('/')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Close all in-progress orders
    cursor.execute("UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'")
    uwagi = request.form.get('uwagi_lidera', '')
    cursor.execute("INSERT INTO raporty_koncowe (data_raportu, lider_uwagi) VALUES (%s, %s)", (date.today(), uwagi))
    conn.commit()
    conn.close()
    
    # 2. Generate reports (Excel + text)
    try:
        xls_path, txt_path, pdf_path = generuj_excel_zmiany(date.today())
    except Exception:
        xls_path = None
        txt_path = None
        pdf_path = None

    # 3. Try opening Outlook (if available)
    try:
        if xls_path:
            otworz_outlook_z_raportem(xls_path, uwagi)
    except Exception:
        app.logger.exception('Outlook open failed')

    # 4. Return ZIP file if generated
    if xls_path or txt_path or pdf_path:
        from zipfile import ZipFile
        zip_name = f"Raport_{date.today()}.zip"
        zip_path = os.path.join('raporty', zip_name)
        try:
            with ZipFile(zip_path, 'w') as z:
                if xls_path and os.path.exists(xls_path):
                    z.write(xls_path, arcname=os.path.basename(xls_path))
                if txt_path and os.path.exists(txt_path):
                    z.write(txt_path, arcname=os.path.basename(txt_path))
                if pdf_path and os.path.exists(pdf_path):
                    z.write(pdf_path, arcname=os.path.basename(pdf_path))
            return send_file(zip_path, as_attachment=True)
        except Exception:
            app.logger.exception('Failed to create/send zip')

    # Fallback: redirect to login if nothing to download
    return redirect('/login')


@main_bp.route('/wyslij_raport_email', methods=['POST'])
def wyslij_raport_email():
    """Email a generated report (placeholder for future functionality)."""
    return redirect('/')
