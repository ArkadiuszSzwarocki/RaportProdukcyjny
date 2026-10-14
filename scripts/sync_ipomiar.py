"""Dedicated read-only collector. Web requests only read its atomic archives."""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.ipomiar_service import ZONE, archive_path, day_string, normalize, devices


def collect(day, config):
    import requests
    path = archive_path(day, config)
    day = day_string(day)
    # Only the documented provider endpoint; no configurable hosts or redirects.
    url = 'https://www.ipomiar.pl/public-api/v1.0/devices/' + config['device'] + '/data'
    payload = []
    source_days = [day]
    if config.get('timezone') == 'UTC':
        source_days.insert(0, str(datetime.fromisoformat(day).date() - timedelta(days=1)))
    with requests.Session() as session:
        session.trust_env = False
        for source_day in source_days:
            with session.get(url, params={'date': source_day}, timeout=(3, 8),
                             allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise ValueError('Provider did not return measurements')
                content = bytearray()
                deadline = time.monotonic() + 15
                for chunk in response.iter_content(16384):
                    content.extend(chunk)
                    if len(content) > 4_000_000 or time.monotonic() > deadline:
                        raise ValueError('Provider response limit exceeded')
                rows = json.loads(content)
                if not isinstance(rows, list):
                    raise ValueError('Invalid sample list')
                payload.extend(rows)
        samples = normalize(payload, day, config)
    # An empty or incompatible response must not replace a useful archive.
    if not samples:
        raise ValueError('No matching temperature or humidity readings')
    if path.exists():
        previous = json.loads(path.read_text(encoding='utf-8'))
        if previous.get('device') == config['device'] and previous.get('day') == day:
            rows = [{'Date': r.get('utc', r['time']), 'Temperature': r.get('temperature'), 'Humidity': r.get('humidity')}
                    for r in previous['samples']]
            old = normalize(rows, day, {'temperature': 'Temperature', 'humidity': 'Humidity'})
            merged = {r['utc']: r for r in old}
            merged.update({r['utc']: r for r in samples})
            samples = [merged[key] for key in sorted(merged)]
    saved = {'day': day, 'device': config['device'],
             'fetched_at': datetime.now(ZONE).isoformat(), 'samples': samples}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(saved, file, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(samples)


def main():
    parser = argparse.ArgumentParser(description='Archive iPomiar readings for AGRO')
    parser.add_argument('--date', help='YYYY-MM-DD; defaults to today and yesterday')
    parser.add_argument('--watch', action='store_true', help='Refresh every 60 seconds')
    args = parser.parse_args()
    while True:
        today = datetime.now(ZONE).date()
        days = [day_string(args.date)] if args.date else [str(today), str(today - timedelta(days=1))]
        failed = False
        configured = devices()
        if not configured:
            print('No devices configured', flush=True)
            return 1
        for config in configured:
            for day in days:
                try:
                    print(f'{day}: {config["name"]}: archived {collect(day, config)} measurements', flush=True)
                except Exception as error:
                    # Do not log device keys, response bodies or exception URLs.
                    print(f'{day}: {config["name"]}: readings unavailable ({type(error).__name__}); archive preserved', flush=True)
                    failed = True
        if not args.watch:
            return int(failed)
        time.sleep(60)


if __name__ == '__main__':
    raise SystemExit(main())
