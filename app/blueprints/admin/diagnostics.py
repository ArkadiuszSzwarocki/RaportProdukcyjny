import html
import json
import os
import re
import time
from collections import deque
from datetime import datetime, timedelta

from flask import current_app, jsonify, render_template, request, session

from app.decorators import admin_required, dynamic_role_required, login_required, masteradmin_required


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _tail_lines_binary(file_path, count, block_size=1024):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'rb') as file_handle:
            file_handle.seek(0, 2)
            file_size = file_handle.tell()
            lines_found = []
            block_end = file_size
            while block_end > 0 and len(lines_found) <= count:
                block_start = max(block_end - block_size, 0)
                file_handle.seek(block_start)
                block = file_handle.read(block_end - block_start)
                lines_found = block.split(b'\n') + lines_found
                if block_start == 0:
                    break
                block_end = block_start
            return [line.decode('utf-8', errors='replace') for line in lines_found[-count:] if line.strip()]
    except Exception:
        return []


def _tail_text(file_path, count):
    if not os.path.exists(file_path):
        return ''
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as file_handle:
            lines = list(deque(file_handle, maxlen=count))
            lines.reverse()
            return ''.join(lines)
    except Exception as error:
        current_app.logger.exception('Failed to read log %s: %s', file_path, error)
        return f'Error reading log: {error}'


def _redact_log_content(text):
    if not text:
        return text
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED_EMAIL]', text)
    text = re.sub(r'(Authorization:\s*Bearer\s+)[A-Za-z0-9\-\._~\+/=]+', r'\1[REDACTED_TOKEN]', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[0-9a-fA-F]{32,}\b', '[REDACTED_KEY]', text)
    text = re.sub(r'\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[REDACTED_JWT]', text)
    text = re.sub(r'https?://[^\s/]+:[^@\s]+@', 'https://[REDACTED_AUTH]@', text)
    return text


def _parse_optional_datetime(raw_value):
    if not raw_value:
        return None

    formats = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%d.%m.%Y %H:%M:%S',
        '%d.%m.%Y %H:%M',
        '%d.%m.%Y',
    ]
    for date_format in formats:
        try:
            return datetime.strptime(raw_value, date_format)
        except Exception:
            continue

    try:
        normalized = raw_value.replace('T', ' ')
        return datetime.strptime(normalized, '%Y-%m-%d %H:%M:%S,%f')
    except Exception:
        try:
            normalized = raw_value.replace('T', ' ')
            return datetime.strptime(normalized, '%Y-%m-%d %H:%M:%S.%f')
        except Exception:
            return None


def _parse_audit_line(line):
    """Parse a single audit.log line into structured fields."""
    if not line:
        return None

    line = str(line).rstrip('\n')
    pattern = re.compile(
        r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?\s+AUDIT:\s+(?P<user>.*?)\s+\[(?P<role>.*?)\]\s+[—-]\s+(?P<action>.*?)(?:\s+[—-]\s+(?P<detail>.*))?$'
    )
    match = pattern.match(line)
    if not match:
        return None

    detail = (match.group('detail') or '').strip()
    user = (match.group('user') or '').strip()
    role = (match.group('role') or '').strip()
    action = (match.group('action') or '').strip()
    ts_raw = (match.group('ts') or '').strip()

    try:
        ts_dt = datetime.strptime(ts_raw, '%Y-%m-%d %H:%M:%S')
    except Exception:
        ts_dt = None

    trigger = ''
    req = ''
    ip = ''

    trigger_match = re.search(r'(?:^|,\s*)trigger=([^,]+)', detail)
    if trigger_match:
        trigger = trigger_match.group(1).strip()

    ui_match = re.search(r'(?:^|,\s*)ui=([^,]+)', detail)
    if ui_match and not trigger:
        trigger = ui_match.group(1).strip()

    req_match = re.search(r'(?:^|,\s*)req=([^,]+)', detail)
    if req_match:
        req = req_match.group(1).strip()

    ip_match = re.search(r'(?:^|,\s*)ip=([^,]+)', detail)
    if ip_match:
        ip = ip_match.group(1).strip()

    return {
        'timestamp': ts_raw,
        'timestamp_dt': ts_dt,
        'user': user,
        'role': role,
        'action': action,
        'detail': detail,
        'trigger': trigger,
        'req': req,
        'ip': ip,
        'raw': line,
    }


def _filter_audit_entries(entries, *, user, action, trigger, ip, date_from, date_to, date_to_raw):
    out = []

    until_bound = None
    if date_to:
        if len((date_to_raw or '').strip()) == 10:
            until_bound = date_to + timedelta(days=1) - timedelta(microseconds=1)
        else:
            until_bound = date_to

    user_q = (user or '').strip().lower()
    action_q = (action or '').strip().lower()
    trigger_q = (trigger or '').strip().lower()
    ip_q = (ip or '').strip().lower()

    for item in entries:
        if user_q and user_q not in str(item.get('user') or '').lower():
            continue
        if action_q and action_q not in str(item.get('action') or '').lower():
            continue
        if trigger_q:
            trigger_value = str(item.get('trigger') or '')
            if trigger_q not in trigger_value.lower():
                continue
        if ip_q and ip_q not in str(item.get('ip') or '').lower():
            continue

        ts_dt = item.get('timestamp_dt')
        if date_from and ts_dt and ts_dt < date_from:
            continue
        if until_bound and ts_dt and ts_dt > until_bound:
            continue
        if (date_from or until_bound) and not ts_dt:
            continue

        out.append(item)

    return out


def register_admin_diagnostics_routes(admin_bp):
    @admin_bp.route('/admin/ustawienia/errors')
    @dynamic_role_required('errors')
    def ustawienia_errors():
        """View server error logs and application traps with structured parsing."""
        error_log_path = os.path.join(_project_root(), 'logs', 'error.log')

        try:
            lines_count = int(request.args.get('lines', 100))
        except ValueError:
            lines_count = 100

        raw_lines = _tail_lines_binary(error_log_path, lines_count)
        parsed_errors = []
        current_entry = None

        for line in raw_lines:
            trap_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\[TRAP_HEADER\] URL: (.*?) \| ACTION: (.*)', line)
            if trap_match:
                if current_entry:
                    parsed_errors.append(current_entry)
                current_entry = {
                    'timestamp': trap_match.group(1),
                    'url': trap_match.group(2),
                    'action': trap_match.group(3),
                    'type': 'TRAP',
                    'lines': [],
                }
                continue

            generic_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ERROR: (.*)', line)
            if generic_match:
                if current_entry:
                    parsed_errors.append(current_entry)
                current_entry = {
                    'timestamp': generic_match.group(1),
                    'url': 'N/A',
                    'action': 'System Error',
                    'type': 'ERROR',
                    'message': generic_match.group(2),
                    'lines': [generic_match.group(2)],
                }
                continue

            if current_entry:
                current_entry['lines'].append(line)
            else:
                current_entry = {'timestamp': 'Unknown', 'url': '?', 'action': '?', 'type': 'MISC', 'lines': [line]}

        if current_entry:
            parsed_errors.append(current_entry)

        parsed_errors.reverse()

        if request.args.get('fragment') == 'true':
            return render_template('ustawienia_errors_fragment.html', errors=parsed_errors, lines=lines_count)

        return render_template('ustawienia_errors.html', errors=parsed_errors, lines=lines_count)

    @admin_bp.route('/admin/ustawienia/errors/clear', methods=['POST'])
    @dynamic_role_required('errors')
    def clear_error_log():
        """Clear the error.log file by truncating it."""
        error_log_path = os.path.join(_project_root(), 'logs', 'error.log')
        try:
            if os.path.exists(error_log_path):
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    f.write(f'--- Log wyczyszczony przez administratora {session.get("login")} o {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ---\n')
                return jsonify({'success': True, 'message': 'Log błędów został wyczyszczony.'})
            else:
                return jsonify({'success': False, 'message': 'Plik logu nie istnieje.'}), 404
        except Exception as e:
            return jsonify({'success': False, 'message': f'Błąd podczas czyszczenia logu: {str(e)}'}), 500

    @admin_bp.route('/admin/master/mqtt')
    @masteradmin_required
    def admin_master_mqtt():
        """Show live MQTT machine data (Pakowaczka, Paletyzator, Owijarka)."""
        from app.services.mqtt_service import get_latest_data
        import time
        data = get_latest_data()
        last_update = data.get('last_update', 0)
        if last_update:
            age_s = int(time.time() - last_update)
            last_update_str = f"{age_s} sek. temu"
        else:
            last_update_str = "Brak danych"

        # Metadane pól – opis każdego klucza
        field_meta = {
            'bpm': {
                'label': 'Wydajność aktualna (BPM)',
                'device': 'Pakowaczka',
                'topic': 'iot-2/type/cMT2108X2/id/agroPakowaczka',
                'mqtt_key': 'wydajnoscAktualna',
                'unit': 'worki/min',
                'desc': 'Bieżąca wydajność maszyny pakującej – liczba worków produkowanych na minutę. Wartość 0 oznacza postój lub brak danych z urządzenia.',
            },
            'counter': {
                'label': 'Licznik globalny (worki)',
                'device': 'Pakowaczka',
                'topic': 'iot-2/type/cMT2108X2/id/agroPakowaczka',
                'mqtt_key': 'licznikGlobalny',
                'unit': 'szt.',
                'desc': 'Globalny licznik całkowitej liczby worków wyprodukowanych od ostatniego resetu licznika na panelu operatorskim pakowaczki.',
            },
            'status': {
                'label': 'Status maszyny',
                'device': 'Pakowaczka',
                'topic': 'iot-2/type/cMT2108X2/id/agroPakowaczka',
                'mqtt_key': 'status',
                'unit': '',
                'desc': 'Aktualny stan pracy pakowaczki. Wartość "PRACA" = kod 4 (maszyna pracuje), "STOP" = kod 0 (maszyna zatrzymana). Inne wartości numeryczne oznaczają specjalne stany (alarm, tryb serwisowy, itp.).',
            },
            'receptura': {
                'label': 'Aktywna receptura',
                'device': 'Pakowaczka',
                'topic': 'iot-2/type/cMT2108X2/id/agroPakowaczka',
                'mqtt_key': 'nazwaReceptury',
                'unit': '',
                'desc': 'Nazwa receptury (programu) aktualnie załadowanej na pakowaczce. Określa parametry workowania: gramaturę, prędkość dozowania, typ opakowania.',
            },
            'pallet_counter': {
                'label': 'Licznik palet (globalny)',
                'device': 'Paletyzator',
                'topic': 'iot-2/type/cMT2108X2/id/agroPaletyzator',
                'mqtt_key': 'licznikPalet_global',
                'unit': 'palet',
                'desc': 'Globalny licznik palet sformowanych przez paletyzator od ostatniego resetu. Każda pełna paleta zwiększa ten licznik o 1. Używany do śledzenia wydajności paletyzatora i kontroli rozliczeń palet.',
            },
            'is_wrapped': {
                'label': 'Paleta owinięta (bit)',
                'device': 'Owijarka',
                'topic': 'iot-2/type/cMT2108X2/id/agroOwijarka',
                'mqtt_key': 'wyjazdPaletaOwinieta',
                'unit': '',
                'desc': 'Bit sygnalizujący wyjazd gotowej, owiniętej palety z owijarki. Wartość True = paleta właśnie opuściła owiniarkę i jest gotowa do odbioru. Bit jest używany przez system do automatycznego naliczania palet.',
            },
        }

        return render_template(
            'admin/mqtt_monitor.html',
            data=data,
            field_meta=field_meta,
            last_update_str=last_update_str,
            last_update_ts=last_update,
        )

    @admin_bp.route('/admin/master/mqtt/api')
    @masteradmin_required
    def admin_master_mqtt_api():
        """JSON endpoint returning current MQTT machine data."""
        from app.services.mqtt_service import get_latest_data
        import time
        data = get_latest_data()
        last_update = data.get('last_update', 0)
        age_s = int(time.time() - last_update) if last_update else None
        return jsonify({
            'success': True,
            'data': data,
            'age_seconds': age_s,
            'last_update_ts': last_update,
        })

    @admin_bp.route('/admin/master/verify')
    @masteradmin_required
    def admin_master_verify():
        """Run the verify_app.py script and return output."""
        import subprocess
        import sys
        script_path = os.path.join(_project_root(), 'scripts', 'verify_app.py')
        try:
            result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=30)
            output = result.stdout + "\n" + result.stderr
            success = (result.returncode == 0)
            return jsonify({'success': success, 'output': output})
        except Exception as e:
            return jsonify({'success': False, 'output': str(e)})

    @admin_bp.route('/admin/master/db-stats')
    @masteradmin_required
    def admin_master_db_stats():
        """Fetch database statistics (tables row counts and sizes) for MasterAdmin dashboard."""
        from app.db import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    table_name AS name, 
                    table_rows AS rows, 
                    round(((data_length + index_length) / 1024 / 1024), 3) AS size_mb 
                FROM information_schema.TABLES 
                WHERE table_schema = DATABASE()
                ORDER BY (data_length + index_length) DESC
            """)
            stats = []
            for name, rows, size_mb in cursor.fetchall():
                stats.append({
                    'name': name,
                    'rows': int(rows or 0),
                    'size_mb': float(size_mb or 0.0)
                })
            return jsonify({'success': True, 'stats': stats})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @admin_bp.route('/admin/master/permissions')
    @masteradmin_required
    def admin_master_permissions():
        """UI to manage role permissions (RBAC)."""
        project_root = _project_root()
        cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                permissions = json.load(f)
        except Exception as e:
            current_app.logger.error(f"Error loading role permissions: {e}")
            permissions = {}
            
        # Standard roles list (excluding masteradmin which is hardcoded bypass)
        roles = ['admin', 'zarzad', 'lider', 'planista', 'laborant', 'magazynier', 'dur', 'pracownik', 'widz']
        
        # Mapping for sorting order to match sidebar
        section_order = {
            'psd': 1,
            'agro': 2,
            'magazyn': 3,
            'raporty': 4,
            'jakosc': 5,
            'sim': 6,
            'ustawienia': 7,
            'admin_analiza': 8,
            'diag': 9
        }
        
        key_to_section = {
            'psd': 'psd',
            'agro': 'agro',
            'magazyn': 'magazyn',
            'inwentaryzacja': 'magazyn',
            'raporty': 'raporty',
            'jakosc': 'jakosc',
            'awarie': 'jakosc',
            'sim': 'sim',
            'ustawienia': 'ustawienia',
            'planista': 'admin_analiza',
            'moje_godziny': 'admin_analiza',
            'wyniki': 'admin_analiza',
            'struktura': 'admin_analiza',
            'centrum': 'diag',
            'baza_danych': 'diag',
            'leaves': 'diag',
            'production': 'diag'
        }

        # Mapping for human-readable labels matching sidebar
        labels = {
            'magazyn.view': 'Wszystkie Magazyny',
            'magazyn.reception': 'Przyjęcie dostawy',
            'magazyn.return': 'Przesunięcia Palet',
            'magazyn.pending': 'Oczekujące Przyjęcia',
            'magazyn.agro_total': 'Suma surowców',
            'magazyn.agro_packaging': 'Opakowania Agro',
            'magazyn.mom': 'Rozliczenie MOM',
            'magazyn.card': 'Skaner & Drukarka',
            'magazyn.inventory': 'Inwentaryzacja',
            'psd.dashboard': 'Dashboard PSD',
            'psd.zasyp': 'Zasyp PSD',
            'psd.bufor': 'Bufor PSD',
            'psd.workowanie': 'Workowanie PSD',
            'psd.magazyn': 'Magazyn PSD',
            'psd.zasyp_summary': 'Podsumowanie zasypów',
            'agro.dashboard': 'Dashboard Agro',
            'agro.zasyp': 'Zasyp Agro',
            'agro.bufor': 'Bufor Agro',
            'agro.workowanie': 'Workowanie Agro',
            'agro.magazyn': 'Magazyn Agro',
            'agro.zasyp_summary': 'Podsumowanie zasypów Agro',
            'agro.pallet_report': 'Raport Palet AGRO',
            'raporty.dostawy': 'Raport Dostaw',
            'raporty.okresowe': 'Raporty Okresowe',
            'raporty.agro_warehouse': 'Raport Magazynu Agro',
            'raporty.agro_production': 'Raport Produkcji Agro',
            'raporty.performance': 'Wydajność (KPI)',
            'ustawienia.system': 'Ustawienia Systemu',
            'ustawienia.zespol': 'Zespół i Konta',
            'ustawienia.logs': 'Logi Systemowe',
            'ustawienia.errors': 'Logi Błędów',
            'ustawienia.backups': 'Kopie zapasowe',
            'planista': 'Plan Produkcji',
            'moje_godziny': 'Moje Godziny',
            'wyniki': 'Wyniki i Statystyki',
            'struktura': 'Struktura Organizacyjna',
            'jakosc.index': 'Strona Jakość',
            'jakosc.analysis': 'Analiza zasypów',
            'awarie': 'Awarie i Usterki',
            'sim.zebra': 'Symulator Zebra',
            'sim.scanner': 'Symulator Skanera',
            'centrum': 'Centrum Sterowania',
            'baza_danych': 'Baza Danych',
            'production.obsada': 'Zarządzanie Obsadą',
            'leaves.view': 'Widok Obsady (Urlopy)',
            'leaves.dodaj': 'Dodawanie do Obsady',
            'leaves.usun': 'Usuwanie z Obsady'
        }

        # Get all pages from config and sort by section then by name
        def sort_key(page):
            prefix = page.split('.')[0]
            section = key_to_section.get(prefix, 'diag')
            return (section_order.get(section, 99), page)

        pages = sorted(permissions.keys(), key=sort_key) if permissions else []
        
        return render_template('admin/permissions_editor.html', 
                               permissions=permissions, 
                               roles=roles, 
                               pages=pages,
                               labels=labels)

    @admin_bp.route('/admin/master/permissions/save', methods=['POST'])
    @masteradmin_required
    def admin_master_permissions_save():
        """API to save role permissions to JSON file."""
        data = request.get_json() or {}
        project_root = _project_root()
        cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
        
        try:
            # We trust the UI sends the full structure for now
            # In a production app, we'd validate the keys
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # CLEAR CACHE if any was used (currently contexts.py reads it every time)
            return jsonify({'success': True, 'message': 'Uprawnienia zostały zapisane pomyślnie!'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Błąd zapisu: {str(e)}'}), 500


    @admin_bp.route('/admin/ustawienia/logs')
    @dynamic_role_required('logs')
    def admin_ustawienia_logs():
        """Admin-only view: show tail of application logs."""
        try:
            last_request = float(session.get('_logs_last_at') or 0)
        except Exception:
            last_request = 0
        now = time.time()
        if now - last_request < 1.5:
            return jsonify({'error': 'Too many requests'}), 429
        session['_logs_last_at'] = now

        try:
            lines = int(request.args.get('lines', '500'))
        except Exception:
            lines = 500
        if lines < 10:
            lines = 10
        if lines > 2000:
            lines = 2000

        query = request.args.get('q', '').strip()
        query_file = request.args.get('file', '').strip()
        since_raw = request.args.get('since', '').strip()
        until_raw = request.args.get('until', '').strip()
        audit_user = request.args.get('audit_user', '').strip()
        audit_action = request.args.get('audit_action', '').strip()
        audit_trigger = request.args.get('audit_trigger', '').strip()
        audit_ip = request.args.get('audit_ip', '').strip()
        audit_from_raw = request.args.get('audit_from', '').strip()
        audit_to_raw = request.args.get('audit_to', '').strip()

        logs_dir = os.path.join(_project_root(), 'logs')
        app_log_path = os.path.join(logs_dir, 'app.log')
        palety_log_path = os.path.join(logs_dir, 'palety.log')
        audit_log_path = os.path.join(logs_dir, 'audit.log')
        frontend_log_path = os.path.join(logs_dir, 'frontend_errors.log')
        db_log_path = os.path.join(logs_dir, 'db_errors.log')
        status_log_path = os.path.join(logs_dir, 'status_changes.log')

        def cap_lines_by_size(path, requested):
            try:
                if not os.path.exists(path):
                    return requested, False
                size = os.path.getsize(path)
                if size > 50 * 1024 * 1024:
                    return min(requested, 300), True
                if size > 10 * 1024 * 1024:
                    return min(requested, 1000), True
                return requested, False
            except Exception:
                return requested, False

        app_lines, app_trunc = cap_lines_by_size(app_log_path, lines)
        pal_lines, pal_trunc = cap_lines_by_size(palety_log_path, lines)
        audit_lines, audit_trunc = cap_lines_by_size(audit_log_path, lines)
        front_lines, front_trunc = cap_lines_by_size(frontend_log_path, lines)
        db_lines, db_trunc = cap_lines_by_size(db_log_path, lines)
        stat_lines, stat_trunc = cap_lines_by_size(status_log_path, lines)

        app_log = _tail_text(app_log_path, app_lines)
        palety_log = _tail_text(palety_log_path, pal_lines)
        audit_log_text = _tail_text(audit_log_path, audit_lines)
        frontend_log = _tail_text(frontend_log_path, front_lines)
        db_log = _tail_text(db_log_path, db_lines)
        status_log = _tail_text(status_log_path, stat_lines)

        try:
            app_log = _redact_log_content(app_log)
            palety_log = _redact_log_content(palety_log)
            audit_log_text = _redact_log_content(audit_log_text)
            frontend_log = _redact_log_content(frontend_log)
            db_log = _redact_log_content(db_log)
            status_log = _redact_log_content(status_log)
        except Exception:
            app_log = html.escape(app_log or '')
            palety_log = html.escape(palety_log or '')
            audit_log_text = html.escape(audit_log_text or '')
            frontend_log = html.escape(frontend_log or '')
            db_log = html.escape(db_log or '')
            status_log = html.escape(status_log or '')

        search_results = None
        raw_files_content = None
        since_dt = _parse_optional_datetime(since_raw)
        until_dt = _parse_optional_datetime(until_raw)
        audit_from_dt = _parse_optional_datetime(audit_from_raw)
        audit_to_dt = _parse_optional_datetime(audit_to_raw)

        parsed_audit_entries = []
        for line in (audit_log_text or '').splitlines():
            parsed = _parse_audit_line(line)
            if parsed:
                parsed_audit_entries.append(parsed)

        has_audit_filters = any([audit_user, audit_action, audit_trigger, audit_ip, audit_from_raw, audit_to_raw])
        audit_filtered = None
        audit_recent = parsed_audit_entries[:200]
        audit_rows = audit_recent
        if has_audit_filters:
            audit_filtered = _filter_audit_entries(
                parsed_audit_entries,
                user=audit_user,
                action=audit_action,
                trigger=audit_trigger,
                ip=audit_ip,
                date_from=audit_from_dt,
                date_to=audit_to_dt,
                date_to_raw=audit_to_raw,
            )
            audit_filtered = list(audit_filtered)
            audit_rows = audit_filtered

        if not query and (query_file or since_dt or until_dt):
            raw_files_content = []
            try:
                if query_file == 'audit':
                    patterns = ['audit.log']
                elif query_file == 'palety':
                    patterns = ['palety.log']
                elif query_file == 'app':
                    patterns = ['app.log']
                elif query_file == 'frontend':
                    patterns = ['frontend_errors.log']
                else:
                    patterns = ['audit.log', 'palety.log', 'app.log', 'frontend_errors.log', 'db_errors.log', 'status_changes.log']

                def try_add_file(file_path, name):
                    try:
                        if os.path.exists(file_path) and os.path.isfile(file_path):
                            max_bytes = 2 * 1024 * 1024
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as file_handle:
                                content = file_handle.read(max_bytes)
                                truncated = False
                                try:
                                    extra = file_handle.read(1)
                                    if extra:
                                        truncated = True
                                except Exception:
                                    pass
                            raw_files_content.append({'name': name, 'path': file_path, 'content': content, 'truncated': truncated})
                    except Exception:
                        return

                if since_dt and until_dt and since_dt.date() == until_dt.date():
                    date_str = since_dt.strftime('%Y-%m-%d')
                    for pattern in patterns:
                        candidate = os.path.join(logs_dir, f'{pattern}.{date_str}')
                        try_add_file(candidate, os.path.basename(candidate))
                elif since_dt and until_dt and since_dt.date() != until_dt.date():
                    current_date = since_dt.date()
                    end_date = until_dt.date()
                    while current_date <= end_date:
                        date_str = current_date.strftime('%Y-%m-%d')
                        for pattern in patterns:
                            candidate = os.path.join(logs_dir, f'{pattern}.{date_str}')
                            try_add_file(candidate, os.path.basename(candidate))
                        current_date = current_date + timedelta(days=1)
                elif since_dt and not until_dt:
                    date_str = since_dt.strftime('%Y-%m-%d')
                    for pattern in patterns:
                        candidate = os.path.join(logs_dir, f'{pattern}.{date_str}')
                        try_add_file(candidate, os.path.basename(candidate))
                elif not since_dt and until_dt:
                    date_str = until_dt.strftime('%Y-%m-%d')
                    for pattern in patterns:
                        candidate = os.path.join(logs_dir, f'{pattern}.{date_str}')
                        try_add_file(candidate, os.path.basename(candidate))
                else:
                    for pattern in patterns:
                        main_path = os.path.join(logs_dir, pattern)
                        try_add_file(main_path, pattern)
                        rotated = [name for name in os.listdir(logs_dir) if name.startswith(pattern + '.')] if os.path.exists(logs_dir) else []
                        rotated.sort(reverse=True)
                        for name in rotated[:3]:
                            candidate = os.path.join(logs_dir, name)
                            try_add_file(candidate, name)
            except Exception:
                raw_files_content = raw_files_content or []

        if query:
            search_results = []
            try:
                if query_file == 'audit':
                    patterns = ['audit.log']
                elif query_file == 'palety':
                    patterns = ['palety.log']
                elif query_file == 'app':
                    patterns = ['app.log']
                elif query_file == 'frontend':
                    patterns = ['frontend_errors.log']
                else:
                    patterns = ['audit.log', 'palety.log', 'app.log', 'frontend_errors.log', 'db_errors.log', 'status_changes.log']

                files = []
                for name in os.listdir(logs_dir):
                    for pattern in patterns:
                        if name.startswith(pattern):
                            files.append(name)
                files.sort(reverse=True)

                max_files = 12
                max_matches = 800
                matches = 0
                timestamp_regex = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[\.,]\d{1,6})?)')

                for file_name in files[:max_files]:
                    file_path = os.path.join(logs_dir, file_name)
                    if not os.path.isfile(file_path):
                        continue
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as file_handle:
                            file_matches = []
                            for index, line in enumerate(file_handle, start=1):
                                if query.lower() not in line.lower():
                                    continue
                                if since_dt or until_dt:
                                    match = timestamp_regex.match(line)
                                    if not match:
                                        continue
                                    timestamp = match.group(1).replace(',', '.')
                                    try:
                                        line_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
                                    except Exception:
                                        try:
                                            line_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                                        except Exception:
                                            continue
                                    if since_dt and line_dt < since_dt:
                                        continue
                                    if until_dt:
                                        if until_dt.hour == 0 and until_dt.minute == 0 and until_dt.second == 0 and len(until_raw) == 10:
                                            until_bound = until_dt + timedelta(days=1) - timedelta(microseconds=1)
                                        else:
                                            until_bound = until_dt
                                        if line_dt > until_bound:
                                            continue
                                file_matches.append({'file': file_name, 'line_no': index, 'line': line.rstrip()})

                            file_matches.reverse()
                            search_results.extend(file_matches)
                            matches += len(file_matches)
                            if matches >= max_matches:
                                break
                    except Exception:
                        continue
                    if matches >= max_matches:
                        break
            except Exception:
                search_results = search_results or []

        is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest') or (request.args.get('fragment') == 'true')
        template_name = 'ustawienia_logs_fragment.html' if is_ajax else 'ustawienia_logs.html'
        return render_template(
            template_name,
            palety_log=palety_log,
            audit_log=audit_log_text,
            app_log=app_log,
            frontend_log=frontend_log,
            db_log=db_log,
            status_log=status_log,
            lines=lines,
            pal_trunc=pal_trunc,
            audit_trunc=audit_trunc,
            app_trunc=app_trunc,
            front_trunc=front_trunc,
            db_trunc=db_trunc,
            stat_trunc=stat_trunc,
            q=query,
            q_file=query_file,
            search_results=search_results,
            raw_files_content=raw_files_content,
            audit_filtered=audit_filtered,
            audit_filters={
                'user': audit_user,
                'action': audit_action,
                'trigger': audit_trigger,
                'ip': audit_ip,
                'from': audit_from_raw,
                'to': audit_to_raw,
                'active': has_audit_filters,
            },
            audit_total_entries=len(parsed_audit_entries),
            audit_rows=audit_rows,
            audit_rows_limited=(not has_audit_filters),
        )