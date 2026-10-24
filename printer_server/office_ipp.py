"""Read-only IPP job correlation. Never infer print completion from printer idle."""
import http.client
import struct
from urllib.parse import urlsplit


def _attribute(tag, name, value):
    name = name.encode('utf-8')
    value = struct.pack('>i', value) if isinstance(value, int) else value.encode('utf-8')
    return bytes([tag]) + struct.pack('>H', len(name)) + name + struct.pack('>H', len(value)) + value


def decode_groups(data):
    if len(data) < 9 or len(data) > 1024 * 1024:
        raise ValueError('Nieprawidłowa odpowiedź IPP.')
    version, code, request_id = struct.unpack('>HHI', data[:8])
    if version not in (0x0100, 0x0101, 0x0200) or code > 0x00ff or request_id != 1:
        raise ValueError('Drukarka odrzuciła odczyt zadań IPP.')
    groups, group, name, pos = [], None, '', 8
    while pos < len(data):
        tag = data[pos]; pos += 1
        if tag == 3:
            return groups
        if tag < 0x10:
            group = {}; groups.append((tag, group)); name = ''; continue
        if group is None or pos + 2 > len(data):
            raise ValueError('Nieprawidłowe atrybuty IPP.')
        length = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
        if pos + length + 2 > len(data):
            raise ValueError('Ucięta odpowiedź IPP.')
        if length:
            name = data[pos:pos+length].decode('utf-8', 'strict')
        pos += length
        size = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
        if not name or pos + size > len(data):
            raise ValueError('Ucięta wartość IPP.')
        value = data[pos:pos+size]; pos += size
        value = struct.unpack('>i', value)[0] if tag in (0x21, 0x23) and size == 4 else value.decode('utf-8', 'replace')
        group.setdefault(name, []).append(value)
    raise ValueError('Brak końca odpowiedzi IPP.')


def _jobs(uri, which):
    parsed = urlsplit(uri)
    transport = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    connection = transport(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80 if parsed.scheme == 'http' else 631), timeout=3)
    payload = struct.pack('>HHI', 0x0101, 0x000a, 1) + b'\x01'
    for tag, name, value in [(0x47,'attributes-charset','utf-8'),(0x48,'attributes-natural-language','en'),
                             (0x45,'printer-uri',uri),(0x44,'which-jobs',which),(0x21,'limit',500)]:
        payload += _attribute(tag, name, value)
    for i, value in enumerate(('job-name','job-id','job-state','job-state-reasons')):
        payload += _attribute(0x44, 'requested-attributes' if i == 0 else '', value)
    try:
        connection.request('POST', parsed.path or '/ipp/print', payload+b'\x03', {'Content-Type':'application/ipp'})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('Odczyt IPP niedostępny.')
        return decode_groups(response.read(1024 * 1024 + 1))
    finally:
        connection.close()


def device_job_status(uri, document_name):
    """Only an exact unique job-name matches. Completed with queued-in-device is not proof."""
    for which in ('completed', 'not-completed'):
        for tag, group in _jobs(uri, which):
            if tag != 2 or group.get('job-name') != [document_name]:
                continue
            state = (group.get('job-state') or [None])[0]
            reasons = set(group.get('job-state-reasons', []))
            if state == 9:
                if reasons & {'queued-in-device','job-queued'}:
                    return 'SENT_TO_PRINTER', 'IPP: przekazano dalej; brak potwierdzenia końca druku.'
                if reasons & {'job-completed-with-errors','completed-with-errors'}:
                    return 'FAILED', 'Drukarka zgłosiła zakończenie z błędami.'
                if reasons & {'job-completed-with-warnings','completed-with-warnings'}:
                    return 'DEVICE_WARNING', 'Drukarka zgłosiła zakończenie z ostrzeżeniami.'
                return 'DEVICE_COMPLETED', 'Drukarka zgłosiła zakończenie dokładnie tego zadania (IPP).'
            if state in (7,8):
                return 'CANCELLED' if state == 7 else 'FAILED', 'Drukarka anulowała lub przerwała zadanie.'
            if state in (4,6):
                return 'ATTENTION', 'Drukarka wstrzymała zadanie: ' + ', '.join(sorted(reasons))
            if state in (3,5):
                return 'DEVICE_PROCESSING', 'Drukarka rozpoznaje zadanie; ' + ', '.join(sorted(reasons))
    return None
