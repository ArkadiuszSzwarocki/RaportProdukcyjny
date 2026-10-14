"""Read archived iPomiar samples without networking in production requests."""
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Warsaw')


def settings():
    return {
        'device': os.getenv('IPOMIAR_AGRO_DEVICE_ID', '').strip(),
        'name': os.getenv('IPOMIAR_AGRO_NAME', 'Hala AGRO'),
        'temperature': os.getenv('IPOMIAR_TEMPERATURE_FIELD', 'Temperature'),
        'humidity': os.getenv('IPOMIAR_HUMIDITY_FIELD', 'Humidity'),
        'directory': Path(os.getenv('IPOMIAR_ARCHIVE_DIR', 'instance/ipomiar')),
    }


def devices():
    """Device keys and field mappings belong to private runtime configuration."""
    config = settings()
    filename = os.getenv('IPOMIAR_CONFIG_FILE')
    if not filename:
        return [config] if config['device'] else []
    try:
        payload = json.loads(Path(filename).read_text(encoding='utf-8'))
        result = []
        for device in payload['devices'][:20]:
            entry = {**config, **device}
            entry['directory'] = config['directory']
            archive_path(date.today(), entry)
            result.append(entry)
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def read_all(day):
    day = day_string(day)
    return [read_day(day, config=config) for config in devices()]


def read_dashboard(day):
    day = day_string(day)
    result = []
    for config in devices():
        data = read_day(day, config=config)
        if not data['latest'] and day == datetime.now(ZONE).date().isoformat():
            directory = archive_path(day, config).parent
            for path in sorted(directory.glob('????-??-??.json'), reverse=True):
                if path.stem > day:
                    continue
                data = read_day(path.stem, config=config)
                if data['latest']:
                    break
        result.append(data)
    return result


def day_string(value):
    return date.fromisoformat(str(value)).isoformat()


def archive_path(day, config=None):
    import re
    config = config or settings()
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', config['device']):
        raise ValueError('Invalid device identifier')
    return config['directory'] / config['device'] / (day_string(day) + '.json')


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def normalize(payload, day, config):
    """Missing readings stay missing; labels are mapped explicitly per device."""
    if not isinstance(payload, list) or len(payload) > 30000:
        raise ValueError('Invalid sample list')
    samples = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            timestamp = datetime.fromisoformat(row['Date'])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=ZoneInfo(config.get('timezone', 'Europe/Warsaw')))
            timestamp = timestamp.astimezone(ZONE)
        except (KeyError, ValueError, TypeError):
            continue
        if timestamp.date().isoformat() != day_string(day):
            continue
        temperature = _number(row.get(config['temperature']))
        humidity = _number(row.get(config['humidity']))
        if humidity is not None and not 0 <= humidity <= 100:
            humidity = None
        if temperature is None and humidity is None:
            continue
        local_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        utc = timestamp.astimezone(timezone.utc).isoformat()
        samples[utc] = {'time': local_time, 'utc': utc, 'temperature': temperature, 'humidity': humidity}
    return [samples[key] for key in sorted(samples)]


def read_day(day, now=None, config=None):
    config = config or settings()
    day = day_string(day)
    result = {'enabled': bool(config['device']), 'name': config['name'], 'day': day,
              'samples': [], 'summary': {}, 'latest': None, 'stale': True,
              'message': 'Brak zapisanych pomiarów', 'fetched_at': None}
    if not result['enabled']:
        result['message'] = 'Pomiary nie są skonfigurowane'
        return result
    try:
        path = archive_path(day, config)
        if path.stat().st_size > 4_000_000:
            raise ValueError('Archive too large')
        saved = json.loads(path.read_text(encoding='utf-8'))
        if saved['day'] != day or saved['device'] != config['device']:
            raise ValueError('Archive mismatch')
        # Revalidate archived samples using the same input contract.
        rows = [{'Date': r.get('utc', r['time']), 'Temperature': r.get('temperature'), 'Humidity': r.get('humidity')}
                for r in saved['samples']]
        samples = normalize(rows, day, {'temperature': 'Temperature', 'humidity': 'Humidity'})
        result['samples'] = samples
        result['fetched_at'] = saved.get('fetched_at')
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return result
    for field in ('temperature', 'humidity'):
        values = [r[field] for r in samples if r[field] is not None]
        result['summary'][field] = ({'min': min(values), 'max': max(values),
                                     'mean': sum(values) / len(values), 'count': len(values)} if values else None)
    if samples:
        latest = samples[-1]
        result['latest'] = latest
        now = now or datetime.now(ZONE)
        timestamp = datetime.fromisoformat(latest['utc'])
        result['stale'] = now - timestamp > timedelta(minutes=15) or timestamp > now + timedelta(minutes=5)
        result['message'] = 'Ostatni pomiar jest starszy niż 15 minut' if result['stale'] else 'Aktualny pomiar'
        result['first'] = samples[0]['time']
        result['last'] = latest['time']
        times = [datetime.fromisoformat(r['utc']) for r in samples]
        result['gaps'] = sum(b - a > timedelta(minutes=15) for a, b in zip(times, times[1:]))
    return result
