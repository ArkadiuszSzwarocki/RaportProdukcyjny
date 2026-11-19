"""Single-container background collector for iPomiar measurements.

Uses an OS-level non-blocking file lock so multi-worker WSGI servers (such as
Gunicorn) run at most one collector loop per shared archive directory while
web requests continue reading atomic JSON archives without network I/O.
"""

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.services.ipomiar_service import ZONE, archive_path, day_string, devices, normalize, settings

_COLLECTOR_LOCK = threading.Lock()
_COLLECTOR_STARTED = False
_LOCK_FILE_HANDLE = None


def has_configured_devices() -> bool:
    """Return True only when real iPomiar device configuration is supplied."""
    if os.getenv('IPOMIAR_AGRO_DEVICE_ID', '').strip():
        return True
    config_file = os.getenv('IPOMIAR_CONFIG_FILE', '').strip()
    if not config_file:
        return False
    return Path(config_file).is_file()


def _poll_interval_seconds() -> int:
    raw = os.getenv('IPOMIAR_POLL_INTERVAL_SECONDS', '60')
    try:
        return max(30, int(raw))
    except (TypeError, ValueError):
        return 60


def _try_acquire_process_lock(directory: Path):
    """Acquire a non-blocking OS lock file so only one worker collects per host."""
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / '.ipomiar_collector.lock'
    handle = open(lock_path, 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt  # pylint: disable=import-error
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(f'{os.getpid()}\n'.encode('ascii'))
        handle.flush()
        return handle
    except OSError:
        handle.close()
        return None


def collect_day(day, config: dict) -> int:
    """Fetch one day of measurements for a single device and write atomically."""
    import requests

    path = archive_path(day, config)
    day = day_string(day)
    # Only the documented provider endpoint; no configurable hosts or redirects.
    url = 'https://www.ipomiar.pl/public-api/v1.0/devices/' + config['device'] + '/data'
    payload = []
    source_days = [day]
    if config.get('timezone') == 'UTC':
        source_days.insert(0, str(datetime.fromisoformat(day).date() - timedelta(days=1)))

    with requests.Session() as http_session:
        http_session.trust_env = False
        for source_day in source_days:
            with http_session.get(
                url,
                params={'date': source_day},
                timeout=(3, 8),
                allow_redirects=False,
                stream=True,
            ) as response:
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
            rows = [
                {'Date': r.get('utc', r['time']), 'Temperature': r.get('temperature'), 'Humidity': r.get('humidity')}
                for r in previous['samples']
            ]
            old = normalize(rows, day, {'temperature': 'Temperature', 'humidity': 'Humidity'})
            merged = {r['utc']: r for r in old}
            merged.update({r['utc']: r for r in samples})
            samples = [merged[key] for key in sorted(merged)]

    saved = {
        'day': day,
        'device': config['device'],
        'fetched_at': datetime.now(ZONE).isoformat(),
        'samples': samples,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file_obj:
            json.dump(saved, file_obj, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(samples)


def collect_once(target_date=None, logger=None) -> bool:
    """Run one collection pass across all configured devices. Returns True if all succeeded."""
    today = datetime.now(ZONE).date()
    days = [day_string(target_date)] if target_date else [str(today), str(today - timedelta(days=1))]
    configured = devices()
    if not configured:
        return False

    all_ok = True
    for config in configured:
        for day in days:
            try:
                count = collect_day(day, config)
                if logger:
                    logger.debug('iPomiar archived %s measurements for %s (%s)', count, config['name'], day)
            except Exception as error:
                # Never log device keys, response bodies or exception URLs.
                if logger:
                    logger.warning(
                        'iPomiar readings unavailable for %s (%s): %s; archive preserved',
                        config['name'],
                        day,
                        type(error).__name__,
                    )
                all_ok = False
    return all_ok


def _collector_loop(interval: int, logger=None) -> None:
    while True:
        try:
            collect_once(logger=logger)
        except Exception as error:
            if logger:
                logger.warning('iPomiar collector cycle failed: %s', type(error).__name__)
        time.sleep(interval)


def start_ipomiar_collector_daemon(logger=None) -> bool:
    """Start the in-process iPomiar collector thread if configured and lock is acquired."""
    global _COLLECTOR_STARTED, _LOCK_FILE_HANDLE
    if not has_configured_devices():
        if logger:
            logger.info('iPomiar collector skipped: no IPOMIAR_CONFIG_FILE or IPOMIAR_AGRO_DEVICE_ID configured')
        return False

    with _COLLECTOR_LOCK:
        if _COLLECTOR_STARTED:
            return False
        archive_dir = settings()['directory']
        lock_handle = _try_acquire_process_lock(archive_dir)
        if lock_handle is None:
            if logger:
                logger.debug('iPomiar collector lock already held by another worker process')
            return False
        _LOCK_FILE_HANDLE = lock_handle
        _COLLECTOR_STARTED = True

    interval = _poll_interval_seconds()
    worker = threading.Thread(
        target=_collector_loop,
        args=(interval, logger),
        name='ipomiar-collector',
        daemon=True,
    )
    worker.start()
    if logger:
        logger.info('iPomiar background collector started (interval=%ss)', interval)
    return True
