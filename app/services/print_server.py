"""Application-side client and queue service for the authenticated print bridge."""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

import requests


def _read_float_env(name: str, default_value: float, minimum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, default_value))
    except (TypeError, ValueError):
        value = float(default_value)
    if minimum is not None:
        value = max(float(minimum), value)
    return value


def _read_int_env(name: str, default_value: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, default_value))
    except (TypeError, ValueError):
        value = int(default_value)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def _zpl_text(value, limit=120):
    return str(value or '').replace('^', '').replace('~', '')[:limit]


class PrintServer:
    """Queue labels and communicate only through the authenticated print bridge."""

    def __init__(self):
        self.bridge_url = self._normalize_bridge_base(
            os.getenv('PRINTER_BRIDGE_URL', 'http://127.0.0.1:3001')
        )
        self.bridge_token = str(os.getenv('PRINTER_BRIDGE_TOKEN') or '').strip()
        self.bridge_connect_timeout = _read_float_env('PRINTER_BRIDGE_CONNECT_TIMEOUT', 2.0, minimum=0.2)
        self.bridge_read_timeout = _read_float_env('PRINTER_BRIDGE_READ_TIMEOUT', 20.0, minimum=1.0)
        self.bridge_start_timeout = _read_float_env('PRINTER_BRIDGE_START_TIMEOUT', 6.0, minimum=1.0)
        self.bridge_autostart = _env_bool('PRINTER_BRIDGE_AUTOSTART', True)
        self.printer_ip = str(os.getenv('PRINTER_IP') or '').strip()
        self.printer_name = str(os.getenv('PRINTER_NAME') or 'Magazyn').strip()
        self.last_job_id = None

        ca_bundle = str(os.getenv('PRINTER_BRIDGE_CA_BUNDLE') or '').strip()
        self.bridge_tls_verify = ca_bundle if ca_bundle else True

    @staticmethod
    def _normalize_bridge_base(raw_base: str | None = None) -> str:
        value = str(raw_base or 'http://127.0.0.1:3001').strip().rstrip('/')
        lowered = value.lower()
        if lowered.endswith('/drukuj-zpl'):
            value = value[:-11]
        elif lowered.endswith('/status'):
            value = value[:-7]
        if '://' not in value:
            value = f'http://{value}'
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('Nieprawidłowy PRINTER_BRIDGE_URL')
        return value.rstrip('/')

    def _bridge_headers(self) -> dict:
        if not self.bridge_token:
            return {}
        return {'Authorization': f'Bearer {self.bridge_token}'}

    def _request_bridge(self, method: str, path: str, **kwargs):
        """Call the single configured bridge endpoint with TLS verification enabled."""
        normalized_path = '/' + str(path or '').lstrip('/')
        url = f'{self.bridge_url}{normalized_path}'
        headers = dict(kwargs.pop('headers', {}) or {})
        headers.update(self._bridge_headers())

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                verify=self.bridge_tls_verify,
                **kwargs,
            )
            return response, self.bridge_url
        except requests.RequestException as first_error:
            if self.bridge_autostart and self._is_local_bridge_target():
                started, _ = self._ensure_bridge_running()
                if started:
                    response = requests.request(
                        method=method,
                        url=url,
                        headers=headers,
                        verify=self.bridge_tls_verify,
                        **kwargs,
                    )
                    return response, self.bridge_url
            raise first_error

    def test_connection(self) -> tuple[bool, str]:
        try:
            response, bridge_base = self._request_bridge('GET', '/status', timeout=2)
            if response.status_code == 200:
                return True, f'Mostek druku aktywny ({bridge_base})'
            return False, f'Mostek zwrócił status {response.status_code}'
        except Exception as exc:
            return False, f'Błąd połączenia z mostkiem: {exc}'

    def list_network_printers(self) -> list[dict]:
        try:
            response, _ = self._request_bridge(
                'GET',
                '/printers',
                timeout=(self.bridge_connect_timeout, min(self.bridge_read_timeout, 8)),
            )
            if response.status_code != 200:
                return []
            body = response.json() if response.content else {}
            items = body.get('printers') if isinstance(body, dict) else []
            if not isinstance(items, list):
                return []
            result = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                target = str(item.get('ip') or '').strip()
                name = str(item.get('name') or item.get('nazwa') or '').strip()
                if target and name:
                    result.append({
                        'name': name,
                        'ip': target,
                        'lokalizacja': str(item.get('lokalizacja') or 'Skonfigurowana'),
                    })
            return result
        except Exception:
            return []

    def _is_local_bridge_target(self) -> bool:
        host = (urlparse(self.bridge_url).hostname or '').lower()
        return host in ('127.0.0.1', 'localhost', '::1')

    def _bridge_host_port(self) -> tuple[str, int]:
        parsed = urlparse(self.bridge_url)
        host = parsed.hostname or '127.0.0.1'
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        return host, int(port)

    @staticmethod
    def _is_port_open(host: str, port: int, timeout: float = 0.35) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _bridge_script_path() -> str:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        return os.path.join(root, 'printer_server', 'server.py')

    @staticmethod
    def _bridge_start_log_path() -> str:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        return os.path.join(root, 'logs', 'printer_server_start.log')

    @staticmethod
    def _bridge_subprocess_env() -> dict:
        env = os.environ.copy()
        env.pop('WERKZEUG_SERVER_FD', None)
        env.pop('WERKZEUG_RUN_MAIN', None)
        return env

    def _is_bridge_running(self) -> bool:
        try:
            response = requests.get(
                f'{self.bridge_url}/status',
                timeout=(min(self.bridge_connect_timeout, 1.0), min(self.bridge_read_timeout, 2.0)),
                verify=self.bridge_tls_verify,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _ensure_bridge_running(self) -> tuple[bool, str]:
        """Autostart is limited to a local bridge process."""
        if not self._is_local_bridge_target():
            return False, 'Autostart mostka jest dozwolony tylko dla localhost.'
        if self._is_bridge_running():
            return True, 'Mostek druku już działa.'
        if not self.bridge_autostart:
            return False, 'Autostart mostka jest wyłączony.'

        host, port = self._bridge_host_port()
        if self._is_port_open(host, port):
            return False, f'Port {port} jest zajęty przez inną usługę.'
        path = self._bridge_script_path()
        if not os.path.isfile(path):
            return False, f'Nie znaleziono serwera druku: {path}'

        log_path = self._bridge_start_log_path()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        try:
            creation_flags = 0x00000010 if (os.name == 'nt' and _env_bool('PRINTER_SERVER_SHOW_CONSOLE')) else 0
            with open(log_path, 'a', encoding='utf-8', errors='replace') as log_handle:
                process = subprocess.Popen(
                    [sys.executable, path],
                    cwd=os.path.dirname(path),
                    creationflags=creation_flags,
                    start_new_session=True,
                    env=self._bridge_subprocess_env(),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )
            deadline = time.time() + self.bridge_start_timeout
            while time.time() < deadline:
                if self._is_bridge_running():
                    return True, 'Mostek druku uruchomiony.'
                if process.poll() is not None:
                    return False, f'Mostek zakończył pracę z kodem {process.returncode}.'
                time.sleep(0.3)
            return False, 'Mostek druku nie odpowiedział w wymaganym czasie.'
        except Exception as exc:
            return False, f'Błąd autostartu mostka: {exc}'

    @staticmethod
    def _format_qty_display(value) -> str:
        if value is None:
            return '0'
        try:
            number = float(value)
            return f'{number:g}'
        except (TypeError, ValueError):
            return _zpl_text(value, 30)

    def build_pallet_label_zpl(self, label_data: dict, copies: int = 1) -> str:
        """Build a stable pallet/raw-material label without executable ZPL input."""
        from app.utils.pallet_id import generate_pallet_id, is_valid_pallet_id
        from app.utils.pallet_label import is_packaging_item

        payload = dict(label_data or {})
        pallet_id = str(payload.get('nr_palety') or payload.get('nrPalety') or '').strip()
        name = str(payload.get('nazwa') or 'Brak nazwy').strip()
        unit = payload.get('jednostka') or payload.get('unit') or payload.get('jm') or 'kg'
        line = str(payload.get('linia') or 'AGRO').strip()
        is_packaging = is_packaging_item(name, unit=unit, typ=payload.get('typ'), pallet_nr=pallet_id)
        if not pallet_id or not is_valid_pallet_id(pallet_id):
            pallet_id = generate_pallet_id(
                line or 'AGRO',
                type='opakowanie' if is_packaging else (payload.get('typ') or 'surowiec'),
                record_id=payload.get('id'),
            )
            payload['nr_palety'] = pallet_id

        title = 'OPAKOWANIE' if is_packaging else 'SUROWIEC'
        unit = 'szt.' if is_packaging else 'kg'
        quantity = self._format_qty_display(payload.get('ilosc'))
        batch = _zpl_text(payload.get('partia') or payload.get('nr_partii') or '---', 60)
        production = _zpl_text(
            payload.get('data') or payload.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d'), 30
        )
        expiry = _zpl_text(payload.get('termin') or payload.get('data_przydatnosci') or '---', 30)
        safe_name = _zpl_text(name, 80)
        safe_id = _zpl_text(pallet_id, 64)
        copies = max(1, min(100, int(copies or 1)))

        qr_data = json.dumps({
            'typ': title,
            'sscc': safe_id,
            'partia': batch,
            'prod': safe_name,
            'ilosc': quantity,
            'jm': unit,
        }, ensure_ascii=False).replace('^', '').replace('~', '')

        return f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{title}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{safe_name}^FS
^FO250,320^BQN,2,12^FDQA,{safe_id}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{safe_id}^FS
^FO40,750^A0N,45,45^FDPARTIA: {batch}^FS
^FO40,825^A0N,45,45^FDPRODUKCJA: {production}^FS
^FO40,900^A0N,45,45^FDTERMIN: {expiry}^FS
^FO40,1070^A0N,60,60^FDILOSC:^FS
^FO40,1140^A0N,85,85^FD{quantity} {unit}^FS
^FO583,975^BQN,2,3^FDQA,{qr_data}^FS
^PQ{copies}
^XZ"""

    def build_finished_product_label_zpl(self, label_data: dict, copies: int = 1) -> str:
        payload = dict(label_data or {})
        pallet_id = _zpl_text(payload.get('nrPalety') or payload.get('nr_palety') or '---', 64)
        name = _zpl_text(payload.get('nazwa') or 'Brak nazwy', 80)
        production = _zpl_text(
            payload.get('data') or payload.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d'), 30
        )
        expiry = _zpl_text(payload.get('data_przydatnosci') or payload.get('termin_przydatnosci') or payload.get('termin'), 30)
        batch = _zpl_text(payload.get('nr_partii') or payload.get('partia') or f"ZLE-{payload.get('plan_id', '')}", 60)
        line = _zpl_text(payload.get('linia') or '', 20)
        quantity = self._format_qty_display(payload.get('ilosc'))
        copies = max(1, min(100, int(copies or 1)))
        title = f'WYROB GOTOWY - {line}' if line else 'WYROB GOTOWY'
        qr_data = json.dumps({
            'typ': title,
            'sscc': pallet_id,
            'prod': name,
            'partia': batch,
            'ilosc': quantity,
            'jm': 'kg',
        }, ensure_ascii=False).replace('^', '').replace('~', '')
        expiry_line = f'^FO40,950^A0N,45,45^FDPRZYDATNOSC: {expiry}^FS' if expiry else ''
        return f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{title}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{name}^FS
^FO250,320^BQN,2,12^FDQA,{pallet_id}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{pallet_id}^FS
^FO40,825^A0N,45,45^FDPRODUKCJA: {production}^FS
^FO40,890^A0N,45,45^FDNR PARTII: {batch}^FS
{expiry_line}
^FO40,1070^A0N,60,60^FDWAGA NETTO:^FS
^FO40,1140^A0N,85,85^FD{quantity} kg^FS
^FO583,975^BQN,2,3^FDQA,{qr_data}^FS
^PQ{copies}
^XZ"""

    def print_pallet_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None, copies: int = 1) -> tuple[bool, str]:
        return self.queue_print_job(
            self.build_pallet_label_zpl(label_data, copies=copies),
            override_ip,
            override_name,
        )

    def print_finished_product_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None, copies: int = 1) -> tuple[bool, str]:
        return self.queue_print_job(
            self.build_finished_product_label_zpl(label_data, copies=copies),
            override_ip,
            override_name,
        )

    def queue_print_job(self, zpl_content: str, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        """Persist a print job; target authorization is enforced again by the bridge."""
        try:
            from app.db import get_db_connection
            from app.repositories.settings_repository import SettingsRepository

            target_ip = str(override_ip or '').strip()
            target_name = str(override_name or '').strip()
            if not target_ip and not target_name:
                try:
                    default_printer = SettingsRepository.get_default_printer_for_line('AGRO')
                except Exception:
                    default_printer = None
                if default_printer:
                    target_ip = str(default_printer.get('ip') or '').strip()
                    target_name = str(default_printer.get('nazwa') or '').strip()
            target_ip = target_ip or self.printer_ip
            target_name = target_name or self.printer_name
            if not target_ip and not target_name:
                return False, 'Brak skonfigurowanej drukarki.'

            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO print_jobs (printer_ip, printer_name, zpl_content, status) "
                    "VALUES (%s, %s, %s, 'PENDING')",
                    (target_ip, target_name, zpl_content),
                )
                self.last_job_id = cursor.lastrowid
                conn.commit()
                return True, 'Dodano do kolejki druku'
            finally:
                conn.close()
        except Exception as exc:
            self.last_job_id = None
            return False, f'Błąd kolejkowania wydruku: {exc}'

    def print_zpl_label(self, zpl_string: str, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        return self.queue_print_job(zpl_string, override_ip, override_name)

    @staticmethod
    def build_login_qr_label_zpl(qr_data: str, login_display: str = '') -> str:
        safe_data = _zpl_text(qr_data, 500)
        safe_login = _zpl_text(login_display, 50)
        label = '^XA\n^CI28\n^PW240\n^LL180\n'
        label += f'^FO20,10^BQN,2,4^FDQA,{safe_data}^FS\n'
        if safe_login:
            label += f'^FO10,145^A0N,22,22^FB220,1,0,C^FD{safe_login}^FS\n'
        label += '^XZ'
        return label

    def print_location_label(self, label_data: dict) -> tuple[bool, str]:
        location = _zpl_text((label_data or {}).get('lokalizacja') or 'BRAK', 60)
        zpl = (
            '^XA^CI28^PW812^LL1214^FO20,20^GB772,1174,4^FS'
            f'^FO60,100^A0N,100,100^FDREGAL: {location}^FS'
            f'^FO60,250^BQN,2,10^FDMA,{location}^FS^XZ'
        )
        return self.queue_print_job(zpl, self.printer_ip, self.printer_name)

    def send_direct_tcp(self, zpl: str, ip: str, port: int = 9100, timeout: float = 3.0) -> tuple[bool, str]:
        """Legacy compatibility: direct TCP is disabled unless explicitly constrained."""
        if not _env_bool('PRINTER_ALLOW_DIRECT_TCP_FALLBACK', False):
            return False, 'Bezpośredni TCP jest wyłączony; użyj uwierzytelnionego mostka.'
        configured_ip = str(self.printer_ip or '').strip()
        if not configured_ip or str(ip or '').strip() != configured_ip:
            return False, 'Cel TCP nie odpowiada skonfigurowanej drukarce.'
        configured_port = _read_int_env('PRINTER_PORT', 9100, minimum=1, maximum=65535)
        if int(port) != configured_port:
            return False, 'Port TCP nie odpowiada konfiguracji drukarki.'
        try:
            payload = zpl if zpl.endswith('\n') else zpl + '\r\n'
            with socket.create_connection((configured_ip, configured_port), timeout=timeout) as sock:
                sock.sendall(payload.encode('utf-8'))
            return True, f'Wydrukowano przez skonfigurowany TCP ({configured_ip}:{configured_port})'
        except Exception as exc:
            return False, f'Błąd TCP: {exc}'

    def _send_to_bridge_once(self, payload: dict, target_hint: str) -> tuple[bool, str, bool]:
        try:
            response, bridge_base = self._request_bridge(
                'POST',
                '/drukuj-zpl',
                json=payload,
                timeout=(self.bridge_connect_timeout, self.bridge_read_timeout),
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.status_code == 200 and body.get('success'):
                return True, 'Wysłano do drukarki przez mostek', False
            message = body.get('message') or f'Błąd mostka (HTTP {response.status_code})'
            return False, f'{message} ({target_hint}, bridge={bridge_base})', False
        except requests.RequestException as exc:
            return False, f'Błąd komunikacji z mostkiem: {exc} ({target_hint})', True
        except Exception as exc:
            return False, f'Błąd komunikacji z mostkiem: {exc} ({target_hint})', False

    def _send_to_bridge(self, payload: dict) -> tuple[bool, str]:
        """Send only through the authenticated bridge; no arbitrary network fallback."""
        target_name = payload.get('drukarka') or self.printer_name
        target_ip = payload.get('ip') or self.printer_ip
        target_hint = f'drukarka={target_name}, ip={target_ip}'
        ok, message, _ = self._send_to_bridge_once(payload, target_hint)
        return ok, message


_printer = None


def get_printer() -> PrintServer:
    global _printer
    if _printer is None:
        _printer = PrintServer()
    return _printer
