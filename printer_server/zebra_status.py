"""Strict Zebra status parsing and counter-based batch completion checks."""
import re
import time


def parse_host_status(raw):
    frames = re.findall(r'\x02([^\x03]+)\x03', raw)
    if len(frames) != 3:
        raise ValueError('Niepełna odpowiedź statusu Zebra')
    rows = [frame.strip().split(',') for frame in frames]
    if [len(row) for row in rows] != [12, 11, 2]:
        raise ValueError('Nieprawidłowy format statusu Zebra')
    try:
        first, second, third = [[int(value) for value in row] for row in rows]
    except ValueError as exc:
        raise ValueError('Nieprawidłowe pola statusu Zebra') from exc
    return {
        'paper_out': bool(first[1]), 'paused': bool(first[2]),
        'formats_pending': first[4], 'buffer_full': bool(first[5]),
        'partial_format': bool(first[7]), 'head_open': bool(second[2]),
        'ribbon_out': bool(second[3]), 'label_waiting': bool(second[7]),
        'labels_remaining': second[8],
        'temperature_error': bool(first[10] or first[11]),
    }


def read_host_status(sock, timeout=1.5):
    deadline = time.monotonic() + timeout
    sock.settimeout(timeout)
    sock.sendall(b'~HS\r\n')
    raw = b''
    while raw.count(b'\x03') < 3 and len(raw) < 8192:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Upłynął czas odczytu statusu Zebra')
        sock.settimeout(remaining)
        chunk = sock.recv(2048)
        if not chunk:
            raise ValueError('Brak pełnej odpowiedzi drukarki Zebra')
        raw += chunk
    return parse_host_status(raw.decode('ascii', errors='strict'))


def status_error(status):
    for key, message in (
        ('paper_out', 'Brak etykiet'), ('paused', 'Drukarka wstrzymana'),
        ('head_open', 'Otwarta głowica'), ('ribbon_out', 'Brak taśmy'),
        ('temperature_error', 'Nieprawidłowa temperatura drukarki'),
    ):
        if status[key]:
            return message
    return None


def read_label_counter(sock, timeout=1.5):
    deadline = time.monotonic() + timeout
    sock.settimeout(timeout)
    sock.sendall(b'! U1 getvar "odometer.total_label_count"\r\n')
    raw = b''
    while b'\n' not in raw and len(raw) < 1024:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Upłynął czas odczytu licznika etykiet')
        sock.settimeout(remaining)
        chunk = sock.recv(256)
        if not chunk:
            raise ValueError('Brak odczytu licznika etykiet')
        raw += chunk
    value = raw.decode('ascii', errors='strict').strip().strip('"')
    if not value.isdigit():
        raise ValueError('Drukarka nie udostępnia liczbowego licznika etykiet')
    return int(value)


def batch_idle(status):
    return not (status['formats_pending'] or status['labels_remaining'] or
                status['partial_format'] or status['buffer_full'] or status['label_waiting'])


def expected_copies(zpl):
    values = re.findall(r'\^PQ(\d+)', zpl)
    if zpl.count('^XA') != 1 or len(values) > 1:
        raise ValueError('Potwierdzanie wymaga jednej partii ZPL')
    copies = int(values[0]) if values else 1
    if not 1 <= copies <= 100:
        raise ValueError('Nieprawidłowa liczba etykiet w partii')
    return copies


def wait_for_batch(sock, baseline, copies, timeout=12.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = read_host_status(sock)
        error = status_error(status)
        if error:
            raise RuntimeError(error)
        counter = read_label_counter(sock)
        delta = counter - baseline
        if delta < 0 or delta > copies:
            raise RuntimeError('Niejednoznaczna zmiana licznika etykiet')
        if delta == copies and batch_idle(status):
            return True
        time.sleep(0.3)
    raise RuntimeError('Nie uzyskano potwierdzenia zakończenia partii etykiet')
