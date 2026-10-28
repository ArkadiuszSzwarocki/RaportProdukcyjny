# cspell:words bigbagi executemany keepalive
"""Publish warehouse invalidations only after a successful inventory commit."""
import hashlib
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
_WAKE = threading.Condition()
_SQL_COMMENTS = re.compile(r'^\s*(?:(?:/\*.*?\*/)|(?:--[^\n]*(?:\n|$))|(?:#[^\n]*(?:\n|$)))', re.S)
_WRITE = re.compile(r"^\s*(?:INSERT(?:\s+IGNORE)?\s+INTO|REPLACE(?:\s+INTO)?|UPDATE(?:\s+IGNORE)?|DELETE\s+FROM)\s+`?(?:[a-zA-Z0-9_]+`?\.)?`?([a-zA-Z0-9_]+)", re.I)
_TABLE = re.compile(r"^(?:magazyn_|palety_|dostawy|dostawa_|agro_workowanie_bigbagi|agro_plan_opakowania|zlecenia_magazynowe)", re.I)

_REPORT_TABLE = re.compile(r'^(?:plan_produkcji(?:_agro)?|plan_agro|przestoje_zasyp|przestoje_produkcyjne|szarze(?:_agro)?|dosypki(?:_agro)?|wiaderka_maluchy|palety_agro|palety_workowanie|obsada_zmiany|zasyp_etapy(?:_parametry)?)$', re.I)

def report_channel(database):
    return str(database) + ':periodic-reports'

def revision_path(database):
    base = Path(os.environ.get('WAREHOUSE_EVENT_DIR') or Path(__file__).resolve().parents[2] / 'instance' / 'warehouse-events')
    return base / (hashlib.sha256(str(database).encode()).hexdigest()[:20] + '.revision')

def revision(database):
    try: return revision_path(database).read_text(encoding='ascii')
    except FileNotFoundError: return '0'

def publish(database):
    path = revision_path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as target: target.write(uuid.uuid4().hex)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    with _WAKE: _WAKE.notify_all()

def observe_connection(conn, database):
    # Keep the connector object itself, including pooled connection behavior.
    if conn.__dict__.get('_warehouse_observed'): return conn
    conn._warehouse_observed = True
    dirty = [False]
    report_dirty = [False]
    original_cursor, original_commit, original_rollback = conn.cursor, conn.commit, conn.rollback
    def notify():
        for pending, channel in ((dirty,database),(report_dirty,report_channel(database))):
            if not pending[0]: continue
            pending[0] = False
            try: publish(channel)
            except OSError:
                import logging
                logging.getLogger(__name__).exception('Cannot publish data change')
    def cursor(*args, **kwargs):
        result = original_cursor(*args, **kwargs)
        for method in ('execute', 'executemany'):
            original = getattr(result, method)
            def execute(sql, *a, _original=original, **kw):
                value = _original(sql, *a, **kw)
                query = sql.decode('utf-8', errors='replace') if isinstance(sql, bytes) else str(sql)
                while _SQL_COMMENTS.match(query):
                    query = _SQL_COMMENTS.sub('', query, count=1)
                match = _WRITE.match(query)
                if match and _TABLE.match(match.group(1)) and result.rowcount != 0:
                    dirty[0] = True
                if match and _REPORT_TABLE.match(match.group(1)) and result.rowcount != 0:
                    report_dirty[0] = True
                if getattr(conn, '_autocommit', False): notify()
                return value
            setattr(result, method, execute)
        return result
    def commit():
        value = original_commit()
        notify()
        return value
    def rollback():
        value = original_rollback()
        dirty[0] = False
        report_dirty[0] = False
        return value
    conn.cursor, conn.commit, conn.rollback = cursor, commit, rollback
    return conn

def stream(database, duration=55):
    # Every reconnect rechecks authentication; no inventory queries in this loop.
    last = revision(database)
    yield 'retry: 3000\nevent: warehouse-change\ndata: ' + last + '\n\n'
    deadline = time.monotonic() + duration
    heartbeat = time.monotonic() + 15
    while time.monotonic() < deadline:
        with _WAKE: _WAKE.wait(timeout=1)
        current = revision(database)
        if current != last:
            last = current
            yield 'event: warehouse-change\ndata: ' + last + '\n\n'
        if time.monotonic() >= heartbeat:
            heartbeat = time.monotonic() + 15
            yield ': keepalive\n\n'


_STREAM_LOCK = threading.Lock()
_STREAM_COUNT = 0


def reserve_stream():
    """Leave at least half of the HTTP worker threads available for normal requests."""
    global _STREAM_COUNT
    threads = max(1, int(os.environ.get('GUNICORN_THREADS', '8' if os.getenv('APP_INSTANCE_MODE') == 'local' else '64')))
    limit = min(threads // 2, max(1, int(os.environ.get('WAREHOUSE_SSE_MAX_CLIENTS', '32'))))
    with _STREAM_LOCK:
        if _STREAM_COUNT >= limit:
            return None
        _STREAM_COUNT += 1
    released = False
    def release():
        nonlocal released
        global _STREAM_COUNT
        with _STREAM_LOCK:
            if not released:
                released = True
                _STREAM_COUNT -= 1
    return release


def reserved_stream(database, release):
    try:
        yield from stream(database)
    finally:
        release()
