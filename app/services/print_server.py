"""
PrintServer — serwer drukowania etykiet ZPL na drukarce Zebra.

Tryby pracy:
  A) bezpośredni TCP (Zebra osiągalna przez sieć — ZPL przez socket na port 9100)
  B) Windows Spooler (drukarka zainstalowana jako drukarka Windows — win32print)

Konfiguracja (w .env lub app config):
  PRINTER_MODE = tcp | windows
  PRINTER_IP   = 192.168.1.100          (dla trybu tcp)
  PRINTER_PORT = 9100
  PRINTER_NAME = ZebraLP2824            (dla trybu windows)
"""

import requests
import urllib3
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
from datetime import datetime

# Wyłączenie ostrzeżeń o certyfikatach self-signed (most działa na https adhoc)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _read_float_env(name: str, default_value: float, minimum: float | None = None) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        value = float(default_value)
    else:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = float(default_value)
    if minimum is not None:
        value = max(float(minimum), value)
    return value


def _read_int_env(name: str, default_value: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        value = int(default_value)
    else:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = int(default_value)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value

class PrintServer:
    def __init__(self):
        # Mostek (bridge) działa zazwyczaj na tej samej maszynie co serwer WWW
        self.bridge_url = os.getenv('PRINTER_BRIDGE_URL', 'http://127.0.0.1:3001')
        self.bridge_connect_timeout = _read_float_env('PRINTER_BRIDGE_CONNECT_TIMEOUT', 2.0, minimum=0.2)
        configured_bridge_read_timeout = _read_float_env('PRINTER_BRIDGE_READ_TIMEOUT', 12.0, minimum=1.0)

        # Mostek może wykonywać kilka prób TCP do drukarki; timeout klienta musi być >=
        # maksymalnemu oknu obsługi pojedynczego żądania /drukuj-zpl.
        tcp_timeout = _read_float_env('PRINTER_TCP_TIMEOUT', 5.0, minimum=0.5)
        tcp_retries = _read_int_env('PRINTER_TCP_RETRIES', 3, minimum=1, maximum=8)
        tcp_retry_delay = _read_float_env('PRINTER_TCP_RETRY_DELAY', 0.6, minimum=0.0)
        estimated_bridge_print_window = (tcp_timeout * tcp_retries) + (tcp_retry_delay * max(0, tcp_retries - 1)) + 3.0

        self.bridge_read_timeout = max(configured_bridge_read_timeout, estimated_bridge_print_window)
        self.bridge_autostart = str(os.getenv('PRINTER_BRIDGE_AUTOSTART', 'true')).strip().lower() in ('1', 'true', 'yes')
        self.bridge_start_timeout = _read_float_env('PRINTER_BRIDGE_START_TIMEOUT', 6.0, minimum=1.0)
        self.printer_ip = os.getenv('PRINTER_IP', '192.168.1.237')
        self.printer_name = "Magazyn"

    def _normalize_bridge_base(self, raw_base: str | None = None) -> str:
        base_value = str(raw_base or self.bridge_url or '').strip().rstrip('/')
        if not base_value:
            base_value = 'http://127.0.0.1:3001'

        lowered = base_value.lower()
        if lowered.endswith('/drukuj-zpl'):
            base_value = base_value[:-11]
        elif lowered.endswith('/status'):
            base_value = base_value[:-7]

        if '://' not in base_value:
            base_value = f'https://{base_value}'

        return base_value.rstrip('/')

    def _bridge_base_candidates(self) -> list[str]:
        primary = self._normalize_bridge_base(self.bridge_url)
        candidates: list[str] = []

        def _append(candidate: str | None):
            value = str(candidate or '').strip().rstrip('/')
            if not value:
                return
            if value.lower() in {item.lower() for item in candidates}:
                return
            candidates.append(value)

        _append(primary)

        parsed = urlparse(primary)
        scheme = (parsed.scheme or '').lower()
        if scheme in ('http', 'https'):
            alt_scheme = 'http' if scheme == 'https' else 'https'
            alt_base = f"{alt_scheme}://{parsed.netloc}{parsed.path or ''}".rstrip('/')
            _append(alt_base)

        return candidates

    def _request_bridge(self, method: str, path: str, **kwargs):
        normalized_path = '/' + str(path or '').lstrip('/')
        last_error = None

        for bridge_base in self._bridge_base_candidates():
            url = f"{bridge_base}{normalized_path}"
            try:
                response = requests.request(method=method, url=url, verify=False, **kwargs)
                # Zapamiętaj działający wariant URL (np. HTTP zamiast HTTPS) dla kolejnych żądań.
                self.bridge_url = bridge_base
                return response, bridge_base
            except requests.RequestException as request_error:
                last_error = request_error
                continue

        if last_error:
            raise last_error
        raise requests.RequestException('Brak dostępnego endpointu mostka druku.')

    def test_connection(self) -> tuple[bool, str]:
        """Sprawdza połączenie z mostkiem druku."""
        try:
            # Sprawdzamy czy sam mostek żyje
            resp, bridge_base = self._request_bridge('GET', '/status', timeout=2)
            if resp.status_code == 200:
                return True, f"Mostek druku aktywny ({bridge_base})"
            return False, f"Mostek zwrócił status {resp.status_code}"
        except Exception as e:
            return False, f"Błąd połączenia z mostkiem: {str(e)}"

    def list_network_printers(self) -> list[dict]:
        """Pobiera listę drukarek widocznych dla mostka druku (sieć LAN)."""
        try:
            resp, _ = self._request_bridge(
                'GET',
                '/printers',
                timeout=(self.bridge_connect_timeout, min(self.bridge_read_timeout, 8)),
            )
            if resp.status_code != 200:
                return []

            body = resp.json() if resp.content else {}
            raw_items = body.get('printers') if isinstance(body, dict) else []
            if not isinstance(raw_items, list):
                return []

            printers = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                ip = str(item.get('ip') or '').strip()
                if not ip:
                    continue
                printers.append(
                    {
                        'name': str(item.get('name') or item.get('nazwa') or f'Drukarka {ip}').strip(),
                        'ip': ip,
                        'lokalizacja': str(item.get('lokalizacja') or 'Sieć').strip(),
                    }
                )
            return printers
        except Exception:
            return []

    def _is_local_bridge_target(self) -> bool:
        parsed = urlparse(self.bridge_url)
        host = (parsed.hostname or '').strip().lower()
        return host in ('127.0.0.1', 'localhost', '::1')

    def _bridge_host_port(self) -> tuple[str, int]:
        parsed = urlparse(self.bridge_url)
        host = parsed.hostname or '127.0.0.1'
        if parsed.port:
            return host, int(parsed.port)
        return host, (443 if (parsed.scheme or '').lower() == 'https' else 80)

    def _is_port_open(self, host: str, port: int, timeout: float = 0.35) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _bridge_script_path(self) -> str:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        return os.path.join(project_root, 'printer_server', 'server.py')

    def _bridge_start_log_path(self) -> str:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        return os.path.join(project_root, 'logs', 'printer_server_start.log')

    def _bridge_subprocess_env(self) -> dict:
        env = os.environ.copy()
        env.pop('WERKZEUG_SERVER_FD', None)
        env.pop('WERKZEUG_RUN_MAIN', None)
        return env

    def _tail_text_file(self, path: str, max_lines: int = 8) -> str:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                lines = handle.readlines()
            return ''.join(lines[-max_lines:]).strip()
        except Exception:
            return ''

    def _is_bridge_running(self) -> bool:
        try:
            resp, _ = self._request_bridge(
                'GET',
                '/status',
                timeout=(min(self.bridge_connect_timeout, 1.0), min(self.bridge_read_timeout, 2.0)),
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _ensure_bridge_running(self) -> tuple[bool, str]:
        if not self._is_local_bridge_target():
            return False, 'Autostart mostka pominięty: PRINTER_BRIDGE_URL nie wskazuje localhost.'

        if self._is_bridge_running():
            return True, 'Mostek druku już działa.'

        host, port = self._bridge_host_port()
        if self._is_port_open(host, port):
            return (
                False,
                f'Port {port} odpowiada, ale endpoint /status nie działa. Możliwy konflikt usługi.',
            )

        server_path = self._bridge_script_path()
        if not os.path.exists(server_path):
            return False, f'Nie znaleziono pliku serwera druku: {server_path}'

        try:
            creation_flags = 0
            show_console = str(os.getenv('PRINTER_SERVER_SHOW_CONSOLE', 'false')).strip().lower() in ('1', 'true', 'yes')
            if os.name == 'nt' and show_console:
                creation_flags = 0x00000010

            log_path = self._bridge_start_log_path()
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

            with open(log_path, 'a', encoding='utf-8', errors='replace') as startup_log:
                startup_log.write(
                    f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AUTOSTART request pid={os.getpid()} exe={sys.executable}\n"
                )
                startup_log.flush()

                process = subprocess.Popen(
                    [sys.executable, server_path],
                    cwd=os.path.dirname(server_path),
                    creationflags=creation_flags,
                    start_new_session=True,
                    env=self._bridge_subprocess_env(),
                    stdout=startup_log,
                    stderr=subprocess.STDOUT,
                )

            deadline = time.time() + max(self.bridge_start_timeout, 1.0)
            while time.time() < deadline:
                if self._is_bridge_running():
                    return True, 'Mostek druku uruchomiony automatycznie.'

                exit_code = process.poll()
                if exit_code is not None:
                    startup_tail = self._tail_text_file(log_path, max_lines=10)
                    if startup_tail:
                        startup_tail = startup_tail.replace('\r', ' ').replace('\n', ' | ')
                        return (
                            False,
                            f'Mostek druku nie uruchomił się (kod procesu: {exit_code}). Log: {startup_tail}',
                        )
                    return (
                        False,
                        f'Mostek druku nie uruchomił się (kod procesu: {exit_code}). Sprawdź log: {log_path}',
                    )

                time.sleep(0.35)

            if self._is_port_open(host, port):
                return (
                    False,
                    f'Port {port} odpowiada, ale endpoint /status (HTTPS) nie jest dostępny. Możliwy konflikt usługi.',
                )

            return (
                False,
                f'Mostek druku nie odpowiedział na porcie {port} po próbie autostartu. Sprawdź log: {log_path}',
            )
        except Exception as error:
            return False, f'Błąd autostartu mostka druku: {error}'

    def _send_to_bridge_once(self, payload: dict, target_hint: str) -> tuple[bool, str, bool]:
        try:
            resp, bridge_base = self._request_bridge(
                'POST',
                '/drukuj-zpl',
                json=payload,
                timeout=(self.bridge_connect_timeout, self.bridge_read_timeout),
            )
            try:
                body = resp.json()
            except ValueError:
                body = {}

            if resp.status_code == 200 and body.get('success'):
                return True, 'Wysłano do drukarki przez mostek', False

            bridge_msg = body.get('message') or f'Błąd mostka (HTTP {resp.status_code})'
            return False, f"{bridge_msg} ({target_hint}, bridge={bridge_base})", False
        except requests.RequestException as e:
            return False, f"Błąd komunikacji z mostkiem: {str(e)} ({target_hint})", True
        except Exception as e:
            return False, f"Błąd komunikacji z mostkiem: {str(e)} ({target_hint})", False

    @staticmethod
    def _format_qty_display(value) -> str:
        if value is not None:
            return str(value).replace('.0', '')
        return '0'

    def build_pallet_label_zpl(self, label_data: dict, copies: int = 1) -> str:
        """Buduje ZPL dla etykiety surowca/opakowania."""
        from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id
        from app.utils.pallet_label import is_packaging_item

        nr_palety = str(label_data.get('nr_palety') or label_data.get('nrPalety') or '').strip()
        product_name = str(label_data.get('nazwa') or 'Brak nazwy').strip()
        jednostka = label_data.get('jednostka') or label_data.get('unit') or label_data.get('jm') or 'kg'
        linia = str(label_data.get('linia') or 'AGRO').strip()

        is_pkg = is_packaging_item(
            product_name,
            unit=jednostka,
            typ=label_data.get('typ'),
            pallet_nr=nr_palety
        )

        if not nr_palety or not is_valid_pallet_id(nr_palety):
            target_type = 'opakowanie' if is_pkg else (label_data.get('typ') or 'surowiec')
            nr_palety = generate_pallet_id(linia or 'AGRO', type=target_type, record_id=label_data.get('id'))
            label_data['nr_palety'] = nr_palety
            label_data['sscc'] = nr_palety
            rec_id = label_data.get('id')
            if rec_id and (isinstance(rec_id, int) or str(rec_id).isdigit()):
                try:
                    from app.db import get_db_connection, get_table_name
                    c_up = get_db_connection()
                    try:
                        cur_up = c_up.cursor()
                        tbl = get_table_name('magazyn_opakowania' if is_pkg else 'magazyn_surowce', linia)
                        cur_up.execute(f"UPDATE {tbl} SET nr_palety = %s WHERE id = %s", (nr_palety, int(rec_id)))
                        c_up.commit()
                    finally:
                        c_up.close()
                except Exception:
                    pass

        nr_partii = str(label_data.get('partia') or label_data.get('nr_partii') or '---').strip()
        data_produkcji = str(label_data.get('data') or label_data.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')).strip()
        data_przydatnosci = str(label_data.get('termin') or label_data.get('data_przydatnosci') or '---').strip()
        qty_display = self._format_qty_display(label_data.get('ilosc'))
        zbiornik = str(label_data.get('zbiornik') or label_data.get('stacja') or '').strip().upper()
        if not zbiornik and label_data.get('lokalizacja'):
            from app.utils.location_validator import is_production_tank_code
            loc_val = str(label_data.get('lokalizacja')).strip().upper()
            if is_production_tank_code(loc_val):
                zbiornik = loc_val

        # FETCH SYMBOL AND TYPE FROM slownik_surowcow
        symbol = ''
        jednostka = label_data.get('jednostka') or label_data.get('unit') or label_data.get('jm') or 'kg'
        db_typ = ''
        try:
            from app.db import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT symbol, typ FROM slownik_surowcow WHERE nazwa = %s", (product_name,))
            row = cur.fetchone()
            if row:
                if row.get('symbol'):
                    symbol = str(row['symbol']).strip()
                if row.get('typ'):
                    db_typ = str(row['typ']).strip()
            cur.close()
            conn.close()
        except Exception:
            pass

        from app.utils.pallet_label import is_packaging_item
        is_pkg = is_packaging_item(
            product_name,
            unit=jednostka,
            typ=label_data.get('typ') or db_typ,
            pallet_nr=nr_palety
        )
        if is_pkg:
            jednostka = 'szt.'

        display_name = f"{symbol} - {product_name}" if symbol else product_name
        
        if is_pkg:
            header_text = f"OPAKOWANIE - {linia}" if linia else "OPAKOWANIE"
        elif zbiornik:
            header_text = f"SUROWIEC -> {zbiornik}"
        else:
            header_text = f"SUROWIEC - {linia}" if linia else "SUROWIEC"

        if jednostka == 'kg':
            waga_line = f"^FO40,1000^A0N,70,70^FDWAGA NETTO:^FS\n^FO40,1100^A0N,100,100^FD{qty_display} kg^FS"
        else:
            waga_line = f"^FO40,1000^A0N,70,70^FDILOSC:^FS\n^FO40,1100^A0N,100,100^FD{qty_display} {jednostka}^FS"

        import json
        qr_details = {
            "sscc": nr_palety,
            "prod": display_name,
            "partia": nr_partii,
            "data_prod": data_produkcji,
            "data_przyd": data_przydatnosci,
            "ilosc": qty_display,
            "jm": jednostka,
            "typ": header_text
        }
        if zbiornik:
            qr_details["zbiornik"] = zbiornik
        qr_details_safe = json.dumps(qr_details, ensure_ascii=False).replace('^', '').replace('~', '')

        return f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{header_text}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{display_name}^FS
^FO250,320^BQN,2,14^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDPARTIA: {nr_partii}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
^FO40,950^A0N,50,50^FDTERMIN: {data_przydatnosci}^FS
{waga_line}
^FO583,975^BQN,2,3^FDQA,{qr_details_safe}^FS
^PQ{copies}
^XZ"""

    def build_finished_product_label_zpl(self, label_data: dict, copies: int = 1) -> str:
        """Buduje ZPL dla etykiety wyrobu gotowego."""
        nr_palety = str(label_data.get('nrPalety') or label_data.get('nr_palety') or '').strip()
        product_name = str(label_data.get('nazwa') or 'Brak nazwy').strip()
        data_produkcji = str(label_data.get('data') or label_data.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')).strip()
        data_przydatnosci = str(label_data.get('data_przydatnosci') or label_data.get('termin_przydatnosci') or label_data.get('termin') or '').strip()
        qty_display = self._format_qty_display(label_data.get('ilosc'))
        nr_palety_lp = label_data.get('nr_palety_lp') or ''
        linia = str(label_data.get('linia') or '').strip()
        nr_plomby = str(label_data.get('nr_plomby') or '').strip()
        nr_partii = str(label_data.get('nr_partii') or label_data.get('partia') or f"ZLE-{label_data.get('plan_id', '')}").strip()

        if not data_przydatnosci:
            try:
                dt_p = datetime.strptime(data_produkcji[:10], '%Y-%m-%d')
                data_przydatnosci = (dt_p.replace(year=dt_p.year + 1) if dt_p.month != 2 or dt_p.day != 29 else dt_p.replace(year=dt_p.year + 1, day=28)).strftime('%Y-%m-%d')
            except Exception:
                pass

        partia_line = f"^FO40,890^A0N,45,45^FDNR PARTII: {nr_partii}^FS" if nr_partii and nr_partii != 'None' else ""
        przydatnosc_line = f"^FO40,950^A0N,45,45^FDPRZYDATNOSC: {data_przydatnosci}^FS" if data_przydatnosci else ""
        plomba_line = f"^FO40,1010^A0N,40,40^FDNR PLOMBY: {nr_plomby}^FS" if nr_plomby else ""
        
        from app.utils.pallet_label import is_packaging_item
        is_pkg = is_packaging_item(
            product_name,
            unit=label_data.get('jednostka') or label_data.get('unit') or label_data.get('jm'),
            typ=label_data.get('typ'),
            pallet_nr=nr_palety
        )

        is_surowiec = label_data.get('is_surowiec') or (product_name.lower() in ('czyszczenie', 'maka mix do lnu', 'mąka mix do lnu')) or ('czyszczenie' in product_name.lower()) or ('maka mix do lnu' in product_name.lower()) or ('mąka mix do lnu' in product_name.lower())
        if 'czyszczenie' in product_name.lower():
            product_name = "Mąka mix do Lnu"

        if is_pkg:
            header_text = f"OPAKOWANIE - {linia}" if linia else "OPAKOWANIE"
            qty_unit = "szt."
            qty_header = "ILOSC:"
        elif is_surowiec:
            header_text = f"SUROWIEC - {linia}" if linia else "SUROWIEC"
            qty_unit = "kg"
            qty_header = "WAGA NETTO:"
        else:
            header_text = f"WYROB GOTOWY - {linia}" if linia else "WYROB GOTOWY"
            qty_unit = "kg"
            qty_header = "WAGA NETTO:"

        import json
        qr_details = {
            "sscc": nr_palety,
            "prod": product_name,
            "lp": str(nr_palety_lp),
            "partia": nr_partii,
            "plomba": nr_plomby,
            "data_prod": data_produkcji,
            "data_przyd": data_przydatnosci,
            "ilosc": qty_display,
            "jm": qty_unit,
            "typ": header_text
        }
        qr_details_safe = json.dumps(qr_details, ensure_ascii=False).replace('^', '').replace('~', '')

        return f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{header_text}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,320^BQN,2,12^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,45,45^FDNR PALETY: {nr_palety_lp}^FS
^FO40,825^A0N,45,45^FDPRODUKCJA: {data_produkcji}^FS
{partia_line}
{przydatnosc_line}
{plomba_line}
^FO40,1070^A0N,60,60^FD{qty_header}^FS
^FO40,1140^A0N,85,85^FD{qty_display} {qty_unit}^FS
^FO583,975^BQN,2,3^FDQA,{qr_details_safe}^FS
^PQ{copies}
^XZ"""

    def print_pallet_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None, copies: int = 1) -> tuple[bool, str]:
        """Wysyła dane palety do kolejki z wygenerowanym kodem ZPL 4x6."""
        zpl_string = self.build_pallet_label_zpl(label_data, copies=copies)
        return self.queue_print_job(zpl_string, override_ip, override_name)

    def print_finished_product_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None, copies: int = 1) -> tuple[bool, str]:
        """Wysyła dane palety wyrobu gotowego do kolejki z wygenerowanym kodem ZPL 4x6."""
        zpl_string = self.build_finished_product_label_zpl(label_data, copies=copies)
        return self.queue_print_job(zpl_string, override_ip, override_name)

    def queue_print_job(self, zpl_content: str, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        """Dodaje etykietę do asynchronicznej kolejki wydruków w bazie danych."""
        try:
            from app.db import get_db_connection
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                target_ip = override_ip
                target_name = override_name
                if not target_ip:
                    try:
                        from app.repositories.settings_repository import SettingsRepository
                        p_row = SettingsRepository.get_default_printer_for_line('AGRO')
                        if p_row:
                            target_ip = p_row.get('ip')
                            target_name = p_row.get('nazwa')
                    except Exception:
                        pass
                target_ip = target_ip or self.printer_ip
                target_name = target_name or self.printer_name
                
                cursor.execute("""
                    INSERT INTO print_jobs (printer_ip, printer_name, zpl_content, status)
                    VALUES (%s, %s, %s, 'PENDING')
                """, (target_ip, target_name, zpl_content))
                job_id = cursor.lastrowid
                conn.commit()
                self.last_job_id = job_id
                return True, "Dodano do kolejki druku"
            finally:
                conn.close()
        except Exception as e:
            import traceback
            error_msg = f"Błąd kolejkowania wydruku: {e}\n{traceback.format_exc()}"
            print(error_msg)
            self.last_job_id = None
            return False, f"Błąd bazy danych: {e}"

    def print_zpl_label(self, zpl_string: str, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        """
        Zamiast wysyłać od razu do drukarki i blokować wątek, zakolejkuj wydruk.
        Wątek w tle (Spooler) wyśle go do mostka/drukarki.
        """
        return self.queue_print_job(zpl_string, override_ip, override_name)

    def build_login_qr_label_zpl(self, qr_data: str, login_display: str = '') -> str:
        """Buduje ZPL dla małej etykiety QR z loginem i hasłem (1cm x 1cm).
        
        Args:
            qr_data: Dane do zakodowania w QR (np. "LOGIN:xxx|PASS:yyy" lub JSON)
            login_display: Opcjonalny tekst do wyświetlenia (np. login użytkownika)
        
        Returns:
            String ZPL gotowy do wysłania na drukarkę Zebra
        """
        # Sanitize ZPL (usuń znaki specjalne które mogą zepsuć ZPL)
        safe_qr_data = str(qr_data or '').replace('^', '').replace('~', '')
        safe_login = str(login_display or '').replace('^', '').replace('~', '')[:20]  # max 20 znaków
        
        # Etykieta 1.5cm x 1.5cm (około 120x120 punktów przy 203 DPI)
        # QR kod współczynnik 2 (mały ale czytelny)
        zpl = "^XA\n"
        zpl += "^CI28\n"  # Kodowanie UTF-8
        zpl += "^PW300\n"  # Szerokość 1.5cm
        zpl += "^LL300\n"  # Wysokość 1.5cm
        
        # QR kod (wyśrodkowany, współczynnik 2)
        zpl += f"^FO50,30^BQN,2,3^FDQA,{safe_qr_data}^FS\n"
        
        # Opcjonalnie wyświetl login pod kodem (mała czcionka)
        if safe_login:
            zpl += f"^FO20,220^A0N,20,20^FB260,1,0,C^FD{safe_login}^FS\n"
        
        zpl += "^XZ"
        return zpl

    def print_location_label(self, label_data: dict) -> tuple[bool, str]:
        """Dla lokalizacji możemy wysłać surowy ZPL (mostek to wspiera)."""
        # Tu możemy zostawić stary ZPL lub przygotować dedykowany dla regałów
        zpl = f"^XA^CI28^PW812^LL1214^FO20,20^GB772,1174,4^FS"
        zpl += f"^FO60,100^A0N,100,100^FDREGAŁ: {label_data.get('lokalizacja')}^FS"
        zpl += f"^FO60,250^BY4^BQN,2,10^FDMA,{label_data.get('lokalizacja')}^FS"
        zpl += "^XZ"
        
        return self.queue_print_job(zpl, self.printer_ip, self.printer_name)

    def _send_to_bridge(self, payload: dict) -> tuple[bool, str]:
        target_name = payload.get('drukarka') or self.printer_name
        target_ip = payload.get('ip') or self.printer_ip
        target_hint = f"drukarka={target_name}, ip={target_ip}"
        ok, message, bridge_unreachable = self._send_to_bridge_once(payload, target_hint)
        if ok:
            return True, message

        if bridge_unreachable:
            return False, f"{message} | Mostek (printer microservice) nie odpowiada."

        return False, message

# Singleton
_printer = None

def get_printer() -> PrintServer:
    global _printer
    if _printer is None:
        _printer = PrintServer()
    return _printer
