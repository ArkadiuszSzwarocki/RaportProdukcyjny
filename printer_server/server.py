"""Authenticated local print bridge for ZPL and office PDF jobs."""

import hmac
import ipaddress
import json
import logging
import os
import signal
import socket
import tempfile
import threading
import time
from functools import wraps

from flask import Flask, jsonify, request

try:
    from printer_server.zebra_status import read_host_status, status_error, batch_idle, read_label_counter, expected_copies, wait_for_batch
except ModuleNotFoundError:
    from zebra_status import read_host_status, status_error, batch_idle, read_label_counter, expected_copies, wait_for_batch

try:
    from flask_cors import CORS
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    CORS = None


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('PrinterServer')
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('PRINTER_BRIDGE_MAX_UPLOAD', str(20 * 1024 * 1024)))


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _read_float_env(name, default_value, minimum=None):
    try:
        value = float(os.getenv(name, default_value))
    except (TypeError, ValueError):
        value = float(default_value)
    return max(float(minimum), value) if minimum is not None else value


def _read_int_env(name, default_value, minimum=None, maximum=None):
    try:
        value = int(os.getenv(name, default_value))
    except (TypeError, ValueError):
        value = int(default_value)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def _load_printer_map():
    """Load printer targets from configuration instead of source-controlled IPs."""
    raw = str(os.getenv('PRINTER_IP_MAP_JSON') or '').strip()
    items = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for name, target in parsed.items():
                    clean_name = str(name or '').strip()
                    clean_target = str(target or '').strip()
                    if clean_name and clean_target:
                        items[clean_name] = clean_target
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error('Invalid PRINTER_IP_MAP_JSON: %s', exc)

    default_target = str(os.getenv('PRINTER_IP') or '').strip()
    if default_target:
        items.setdefault(str(os.getenv('PRINTER_NAME') or 'Magazyn'), default_target)
    return items


PRINTER_IP_MAP = _load_printer_map()
DEFAULT_PRINTER_TCP_TIMEOUT = _read_float_env('PRINTER_TCP_TIMEOUT', 5.0, minimum=0.5)
DEFAULT_PRINTER_TCP_RETRIES = _read_int_env('PRINTER_TCP_RETRIES', 3, minimum=1, maximum=5)
DEFAULT_PRINTER_TCP_RETRY_DELAY = _read_float_env('PRINTER_TCP_RETRY_DELAY', 0.6, minimum=0.0)
DEFAULT_PRINTER_PORT = _read_int_env('PRINTER_PORT', 9100, minimum=1, maximum=65535)
MAX_COPIES = _read_int_env('PRINTER_MAX_COPIES', 20, minimum=1, maximum=100)
MAX_ZPL_BYTES = _read_int_env('PRINTER_MAX_ZPL_BYTES', 2 * 1024 * 1024, minimum=1024)


def _allowed_origins():
    raw = str(os.getenv('PRINTER_BRIDGE_ALLOWED_ORIGINS') or '').strip()
    return [item.strip() for item in raw.split(',') if item.strip()]


if CORS is not None and _allowed_origins():
    CORS(
        app,
        resources={r'/*': {
            'origins': _allowed_origins(),
            'methods': ['GET', 'POST', 'OPTIONS'],
            'allow_headers': [
                'Content-Type', 'Authorization', 'X-Requested-With',
                'X-Printer-Bridge-Token',
            ],
        }},
    )


@app.after_request
def _security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    origin = request.headers.get('Origin')
    if origin and origin in _allowed_origins():
        response.headers['Access-Control-Allow-Private-Network'] = 'true'
    return response


def _configured_token():
    return str(os.getenv('PRINTER_BRIDGE_TOKEN') or '').strip()


def _supplied_token():
    header = str(request.headers.get('Authorization') or '').strip()
    if header.lower().startswith('bearer '):
        return header[7:].strip()
    return str(request.headers.get('X-Printer-Bridge-Token') or '').strip()


def _require_bridge_auth(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        if app.config.get('TESTING'):
            return func(*args, **kwargs)
        expected = _configured_token()
        if not expected:
            logger.error('PRINTER_BRIDGE_TOKEN is not configured; protected bridge request denied')
            return jsonify({'success': False, 'message': 'Mostek druku nie jest skonfigurowany.'}), 503
        supplied = _supplied_token()
        if not supplied or not hmac.compare_digest(expected, supplied):
            return jsonify({'success': False, 'message': 'Brak autoryzacji.'}), 401
        return func(*args, **kwargs)
    return decorated


def _normalize_network_target(value):
    target = str(value or '').strip()
    if not target:
        return None
    if target.upper() == 'USB':
        return 'USB'
    if ':' in target and target.count(':') == 1:
        raise ValueError('Port drukarki nie może być przekazany w żądaniu.')
    try:
        addr = ipaddress.ip_address(target)
    except ValueError as exc:
        raise ValueError('Nieprawidłowy adres IP drukarki.') from exc
    if not _env_bool('PRINTER_ALLOW_PUBLIC_TARGETS', False):
        if not (addr.is_private or addr.is_loopback or addr.is_link_local):
            raise ValueError('Dozwolone są wyłącznie skonfigurowane adresy sieci lokalnej.')
    return str(addr)


def _resolve_zpl_target(data):
    printer_name = str(data.get('drukarka') or '').strip()
    requested_ip = str(data.get('ip') or '').strip()

    if app.config.get('TESTING') and requested_ip:
        return _normalize_network_target(requested_ip), printer_name or None

    if printer_name and printer_name in PRINTER_IP_MAP:
        return _normalize_network_target(PRINTER_IP_MAP[printer_name]), printer_name

    if requested_ip:
        normalized = _normalize_network_target(requested_ip)
        allowed = {
            _normalize_network_target(target)
            for target in PRINTER_IP_MAP.values()
            if str(target or '').strip()
        }
        if normalized in allowed:
            matched_name = next(
                (
                    name for name, target in PRINTER_IP_MAP.items()
                    if _normalize_network_target(target) == normalized
                ),
                None,
            )
            return normalized, matched_name

    raise ValueError('Drukarka nie znajduje się na skonfigurowanej liście dozwolonych celów.')


def _candidate_ports():
    raw = str(os.getenv('PRINTER_TCP_PORTS') or '').strip()
    if not raw:
        return [DEFAULT_PRINTER_PORT]
    ports = []
    for value in raw.split(','):
        try:
            port = int(value.strip())
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports or [DEFAULT_PRINTER_PORT]


def wyslij_do_drukarki_win32(zpl, printer_name=None):
    """Send raw ZPL through a locally installed Windows printer."""
    send_started = False
    try:
        import win32print
        target_name = printer_name or win32print.GetDefaultPrinter()
        hprinter = win32print.OpenPrinter(target_name)
        try:
            job_id = win32print.StartDocPrinter(hprinter, 1, ('Etykieta ZPL', None, 'RAW'))
            win32print.StartPagePrinter(hprinter)
            payload = zpl if zpl.endswith('\n') else zpl + '\r\n'
            send_started = True
            win32print.WritePrinter(hprinter, payload.encode('utf-8'))
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
            logger.info('Windows spooler accepted print job %s', job_id)
            return True
        finally:
            win32print.ClosePrinter(hprinter)
    except Exception as exc:
        if send_started:
            raise PrintOutcomeUnknown(f'Wynik wydruku Windows niepewny: {exc}') from exc
        raise RuntimeError(f'Błąd bufora Windows: {exc}') from exc


def sprawdz_stan_fizyczny_zebra(tcp_socket, timeout=1.5):
    try:
        error = status_error(read_host_status(tcp_socket, timeout))
        return (False, error) if error else (True, 'Status Zebra odczytany')
    except Exception as exc:
        return False, f'Brak wiarygodnego statusu Zebra: {exc}'


_printer_lock = threading.Lock()


class PrintOutcomeUnknown(RuntimeError):
    """The send began; resending could produce duplicate labels."""


def wyslij_do_drukarki(zpl, ip, port=None, timeout=None, retries=None, retry_delay=None, printer_name=None):
    """Send ZPL to an already validated target using configured ports only."""
    with _printer_lock:
        ip_str = _normalize_network_target(ip)
        if ip_str == 'USB':
            return wyslij_do_drukarki_win32(zpl, printer_name)

        payload = str(zpl or '')
        if len(payload.encode('utf-8')) > MAX_ZPL_BYTES:
            raise ValueError('ZPL przekracza dopuszczalny rozmiar.')
        if not payload.endswith('\n'):
            payload += '\r\n'

        tcp_timeout = DEFAULT_PRINTER_TCP_TIMEOUT if timeout is None else max(0.5, float(timeout))
        attempts = DEFAULT_PRINTER_TCP_RETRIES if retries is None else max(1, min(5, int(retries)))
        pause_s = DEFAULT_PRINTER_TCP_RETRY_DELAY if retry_delay is None else max(0.0, float(retry_delay))
        ports = [int(port)] if port is not None else _candidate_ports()
        last_error = 'Błąd połączenia z drukarką'

        for target_port in ports:
            if not 1 <= int(target_port) <= 65535:
                continue
            for attempt in range(1, attempts + 1):
                send_started = False
                try:
                    with socket.create_connection((ip_str, int(target_port)), timeout=tcp_timeout) as sock:
                        verified_targets = {value.strip() for value in os.getenv('PRINTER_VERIFY_LABEL_COUNT_IPS', '').split(',') if value.strip()}
                        verify_count = ip_str in verified_targets
                        if verify_count:
                            status = read_host_status(sock)
                            error = status_error(status)
                            if error or not batch_idle(status):
                                raise ValueError(error or 'Drukarka ma niezakończoną partię etykiet')
                            baseline = read_label_counter(sock)
                            copies = expected_copies(payload)
                        send_started = True
                        sock.sendall(payload.encode('utf-8'))
                        if verify_count:
                            wait_for_batch(sock, baseline, copies)
                            return True
                        ok, message = sprawdz_stan_fizyczny_zebra(sock, timeout=1.5)
                        if not ok:
                            raise RuntimeError(message)
                    logger.info('Print accepted by configured target %s:%s', ip_str, target_port)
                    return True
                except Exception as exc:
                    if send_started:
                        raise PrintOutcomeUnknown(f'Wynik wydruku niepewny: {exc}; sprawdź drukarkę przed ponowieniem') from exc
                    if isinstance(exc, ValueError):
                        raise
                    last_error = str(exc)
                    if attempt < attempts and pause_s:
                        time.sleep(pause_s)
        raise RuntimeError(f'{last_error} (po próbach TCP)')


def _copy_count(data, payload):
    raw = data.get('copies')
    if raw is None and isinstance(payload, dict):
        raw = payload.get('copies')
        if raw is None and isinstance(payload.get('palletData'), dict):
            raw = payload['palletData'].get('copies')
    try:
        return max(1, min(MAX_COPIES, int(raw or 1)))
    except (TypeError, ValueError):
        return 1


def _sanitize_zpl_text(value, limit=80):
    return str(value or '').replace('^', '').replace('~', '')[:limit]


def _build_zpl(data, copies):
    payload = data.get('dane')
    if isinstance(payload, str):
        zpl = payload
        if not zpl.startswith('^XA') or '^XZ' not in zpl:
            raise ValueError('Nieprawidłowy dokument ZPL.')
        if copies > 1 and '^PQ' not in zpl:
            zpl = zpl.rsplit('^XZ', 1)[0] + f'^PQ{copies}\n^XZ'
        return zpl

    if not isinstance(payload, dict):
        raise ValueError('Pole dane musi być obiektem JSON lub dokumentem ZPL.')
    p = payload.get('palletData') if isinstance(payload.get('palletData'), dict) else payload

    pallet_id = _sanitize_zpl_text(
        p.get('sscc') or p.get('nr_palety') or p.get('nrPalety')
        or p.get('displayId') or p.get('id') or 'Brak ID',
        64,
    )
    name = _sanitize_zpl_text(
        p.get('nazwa') or p.get('product_name') or p.get('productName') or 'Brak Nazwy',
        60,
    )
    batch = _sanitize_zpl_text(
        p.get('batchNumber') or p.get('nr_partii') or p.get('batchId') or p.get('partia') or '---',
        50,
    )
    production_date = _sanitize_zpl_text(
        p.get('dataProdukcji') or p.get('data_produkcji') or p.get('productionDate') or p.get('data') or '---',
        24,
    ).split('T')[0]
    expiry_date = _sanitize_zpl_text(
        p.get('dataPrzydatnosci') or p.get('data_przydatnosci') or p.get('expiryDate') or p.get('termin') or '---',
        24,
    ).split('T')[0]

    weight_value = (
        p.get('currentWeight') or p.get('qty') or p.get('quantityKg')
        or p.get('producedWeight') or p.get('waga_netto') or p.get('waga')
        or p.get('ilosc') or 0
    )
    try:
        number = float(weight_value)
        weight = f'{number:.0f}' if number.is_integer() else f'{number:.2f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        weight = _sanitize_zpl_text(weight_value, 20)

    unit = _sanitize_zpl_text(p.get('unit') or p.get('jednostka') or 'kg', 10)
    if unit.lower() in ('szt.', 'szt', 'pcs'):
        weight_heading = 'ILOSC:'
        weight_text = f'{weight} szt.'
    else:
        weight_heading = 'WAGA NETTO:'
        weight_text = f'{weight} kg'

    kind = str(data.get('typ') or p.get('p_type') or '').lower()
    if 'packaging' in kind or 'opakowanie' in kind:
        title = 'OPAKOWANIE'
    elif 'raw' in kind or 'surowiec' in kind:
        title = 'SUROWIEC'
    else:
        title = 'WYROB GOTOWY'

    zpl = '^XA^CI28\n^PW800\n^LL1200\n^MNG\n^PON\n'
    zpl += '^FO10,10^GB780,1180,4^FS\n'
    zpl += f'^FO40,50^A0N,40,40^FD{title}^FS\n'
    zpl += f'^FO40,110^A0N,60,60^FB720,2,0,L^FD{name}^FS\n'
    zpl += f'^FO250,190^BQN,2,12^FDQA,{pallet_id}^FS\n'
    zpl += f'^FO40,510^A0N,35,35^FB720,1,0,C^FD{pallet_id}^FS\n'
    zpl += f'^FO60,560^A0N,35,35^FDPARTIA: {batch}^FS\n'
    zpl += f'^FO60,610^A0N,35,35^FDPRODUKCJA: {production_date}^FS\n'
    zpl += f'^FO60,660^A0N,35,35^FDWAZNOSC: {expiry_date}^FS\n'
    zpl += f'^FO60,950^A0N,72,72^FD{weight_heading}^FS\n'
    zpl += f'^FO60,1030^A0N,100,100^FD{weight_text}^FS\n'
    if copies > 1:
        zpl += f'^PQ{copies}\n'
    zpl += '^XZ'
    return zpl


@app.route('/status', methods=['GET'])
def status():
    return jsonify({'success': True, 'message': 'Serwer druku działa.'})


@app.route('/printers', methods=['GET'])
@_require_bridge_auth
def printers():
    return jsonify({
        'success': True,
        'printers': [
            {'name': name, 'ip': target, 'lokalizacja': 'Skonfigurowana'}
            for name, target in PRINTER_IP_MAP.items()
        ],
    })


@app.route('/shutdown', methods=['POST'])
@_require_bridge_auth
def shutdown():
    if not _env_bool('PRINTER_BRIDGE_ALLOW_SHUTDOWN', False):
        return jsonify({'success': False, 'message': 'Zdalne wyłączenie jest wyłączone.'}), 403
    os.kill(os.getpid(), signal.SIGTERM)
    return jsonify({'success': True, 'message': 'Serwer druku jest wyłączany.'})


@app.route('/drukuj-zpl', methods=['POST'])
@_require_bridge_auth
def drukuj_zpl():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Wymagany obiekt JSON.'}), 400
    try:
        target_ip, printer_name = _resolve_zpl_target(data)
        copies = _copy_count(data, data.get('dane'))
        zpl = _build_zpl(data, copies)
        if len(zpl.encode('utf-8')) > MAX_ZPL_BYTES:
            return jsonify({'success': False, 'message': 'ZPL jest zbyt duży.'}), 413
        wyslij_do_drukarki(zpl, target_ip, printer_name=printer_name)
        verified = target_ip in {value.strip() for value in os.getenv('PRINTER_VERIFY_LABEL_COUNT_IPS', '').split(',') if value.strip()}
        return jsonify({'success': True, 'confirmation': 'label_counter' if verified else 'sent', 'copies': expected_copies(zpl) if verified else None})
    except PrintOutcomeUnknown as exc:
        return jsonify({'success': False, 'outcome_unknown': True, 'message': str(exc)}), 409
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        logger.exception('Print job failed')
        return jsonify({'success': False, 'message': str(exc)}), 502


def _pdf_target():
    """Resolve a PDF printer only from the configured allowlist."""
    printer_name = str(request.form.get('drukarka') or '').strip()
    requested_ip = str(request.form.get('ip') or '').strip()

    if printer_name:
        if printer_name not in PRINTER_IP_MAP:
            raise ValueError('Drukarka PDF nie znajduje się na skonfigurowanej liście.')
        return printer_name

    if requested_ip:
        normalized = _normalize_network_target(requested_ip)
        for name, value in PRINTER_IP_MAP.items():
            clean_value = str(value or '').strip()
            if not clean_value or clean_value.upper() == 'USB':
                continue
            try:
                allowed_target = _normalize_network_target(clean_value)
            except ValueError:
                continue
            if allowed_target == normalized:
                return name
        raise ValueError('Drukarka PDF nie znajduje się na skonfigurowanej liście.')

    raise ValueError('Wskaż skonfigurowaną drukarkę PDF.')


@app.route('/drukuj-pdf', methods=['POST'])
@_require_bridge_auth
def drukuj_pdf():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Brak pliku PDF.'}), 400
    uploaded = request.files['file']
    if not str(uploaded.filename or '').lower().endswith('.pdf'):
        return jsonify({'success': False, 'message': 'Dozwolone są wyłącznie pliki PDF.'}), 400
    try:
        target_printer = _pdf_target()
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400

    fd, pdf_path = tempfile.mkstemp(suffix='.pdf', prefix='drukowanie_')
    os.close(fd)
    uploaded.save(pdf_path)
    try:
        import win32api
        win32api.ShellExecute(0, 'printto', pdf_path, f'"{target_printer}"', '.', 0)
        time.sleep(2)
        return jsonify({'success': True})
    except Exception as exc:
        logger.exception('PDF print failed')
        return jsonify({'success': False, 'message': f'Błąd druku PDF: {exc}'}), 502
    finally:
        try:
            os.remove(pdf_path)
        except OSError:
            pass


if __name__ == '__main__':
    bind_host = str(os.getenv('PRINTER_BRIDGE_HOST') or '127.0.0.1').strip()
    port = _read_int_env('PRINTER_BRIDGE_PORT', 3001, minimum=1, maximum=65535)
    token = _configured_token()
    if bind_host not in ('127.0.0.1', 'localhost', '::1') and not token:
        raise RuntimeError(
            'PRINTER_BRIDGE_TOKEN is required when the print bridge listens beyond localhost.'
        )

    cert_file = str(os.getenv('PRINTER_BRIDGE_TLS_CERT') or '').strip()
    key_file = str(os.getenv('PRINTER_BRIDGE_TLS_KEY') or '').strip()
    ssl_context = None
    if cert_file or key_file:
        if not cert_file or not key_file or not os.path.isfile(cert_file) or not os.path.isfile(key_file):
            raise RuntimeError('Both PRINTER_BRIDGE_TLS_CERT and PRINTER_BRIDGE_TLS_KEY must exist.')
        ssl_context = (cert_file, key_file)

    logger.info('Print bridge listening on %s:%s', bind_host, port)
    app.run(host=bind_host, port=port, ssl_context=ssl_context)
