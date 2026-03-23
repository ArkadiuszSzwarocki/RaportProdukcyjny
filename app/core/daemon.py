"""Background daemon threads for maintenance tasks."""

import os
import time
import threading
from flask import current_app

# Global set to track reminded palety to avoid duplicate log entries
_reminded_palety = set()

# Global logger for palety-specific events
palety_logger = None


def _safe_log_info(msg, *args, **kwargs):
    try:
        if palety_logger:
            palety_logger.info(msg, *args, **kwargs)
        else:
            print(msg % args if args else msg)
    except Exception:
        try:
            print(msg)
        except Exception:
            pass


def _safe_log_warning(msg, *args, **kwargs):
    try:
        if palety_logger:
            palety_logger.warning(msg, *args, **kwargs)
        else:
            print('WARNING: ' + (msg % args if args else msg))
    except Exception:
        try:
            print('WARNING: ' + msg)
        except Exception:
            pass


def _safe_log_exception(msg, *args, **kwargs):
    try:
        if palety_logger:
            palety_logger.exception(msg, *args, **kwargs)
        else:
            print('EXCEPTION: ' + (msg % args if args else msg))
    except Exception:
        try:
            print('EXCEPTION: ' + msg)
        except Exception:
            pass


def _cleanup_old_reports(folder='raporty', max_age_hours=24, interval_seconds=3600):
    """Background thread: removes files in `folder` older than `max_age_hours` every `interval_seconds`.
    
    Args:
        folder: Directory to clean up
        max_age_hours: Maximum age in hours before removal
        interval_seconds: How often to run cleanup check
    """
    try:
        while True:
            try:
                if os.path.exists(folder):
                    now = time.time()
                    max_age = max_age_hours * 3600
                    for name in os.listdir(folder):
                        path = os.path.join(folder, name)
                        try:
                            if os.path.isfile(path):
                                mtime = os.path.getmtime(path)
                                if now - mtime > max_age:
                                    try:
                                        os.remove(path)
                                        _safe_log_info('Removed old report file: %s', path)
                                    except Exception:
                                        _safe_log_exception('Failed to remove file: %s', path)
                        except Exception:
                            _safe_log_exception('Error checking file: %s', path)
            except Exception:
                _safe_log_exception('Error in cleanup loop')
            time.sleep(interval_seconds)
    except Exception:
        current_app.logger.exception('Cleanup thread terminating unexpectedly')


def _monitor_unconfirmed_palety(threshold_minutes=10, interval_seconds=60):
    """Background thread: logs reminders for unconfirmed palety (waga==0).
    
    Tracks reminded palety in _reminded_palety set to avoid duplicate log entries.
    
    Args:
        threshold_minutes: Minutes old before reminder is logged
        interval_seconds: How often to check for unconfirmed palety
    """
    from app.db import get_db_connection
    from app.dto.paleta import PaletaDTO
    
    try:
        while True:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.waga = 0 AND COALESCE(pw.status,'') <> 'przyjeta' AND TIMESTAMPDIFF(MINUTE, pw.data_dodania, NOW()) >= %s",
                    (threshold_minutes,)
                )
                raw_rows = cursor.fetchall()
                # Format dates in Python — unpack SELECT results in expected order
                rows = []
                for r in raw_rows:
                    try:
                        pid, plan_id, produkt, dt = r
                    except Exception:
                        # Fallback: use DTO if cursor returned unexpected format
                        dto = PaletaDTO.from_db_row(r)
                        pid, plan_id, produkt, dt = dto.id, dto.plan_id, dto.produkt, dto.data_dodania
                    try:
                        sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                    except Exception:
                        sdt = str(dt)
                    rows.append((pid, plan_id, produkt, sdt))
                try:
                    conn.close()
                except Exception:
                    pass

                for r in rows:
                    try:
                        pid = r[0]
                        if pid in _reminded_palety:
                            continue
                        msg = f"Niepotwierdzona paleta id={r[0]}, plan_id={r[1]}, produkt={r[2]}, dodana={r[3]} - brak potwierdzenia > {threshold_minutes}min"
                        if palety_logger:
                            palety_logger.warning(msg)
                        _safe_log_warning(msg)
                        _reminded_palety.add(pid)
                    except Exception:
                        _safe_log_exception('Error processing unconfirmed paleta row')
            except Exception:
                _safe_log_exception('Error in unconfirmed palety monitor loop')
            time.sleep(interval_seconds)
    except Exception:
        _safe_log_exception('Unconfirmed palety monitor terminating unexpectedly')


def start_daemon_threads(app, cleanup_enabled=False):
    """Start background daemon threads.
    
    Args:
        app: Flask application instance
        cleanup_enabled: Whether to start cleanup thread (default: False)
    """
    global palety_logger
    
    # Configure palety logger
    try:
        palety_logger = app.logger  # For now, use app logger
    except Exception:
        palety_logger = None
    
    # Start cleanup thread (optional)
    if cleanup_enabled:
        try:
            cleanup_thread = threading.Thread(
                target=_cleanup_old_reports,
                kwargs={'folder': 'raporty', 'max_age_hours': 24, 'interval_seconds': 3600},
                daemon=True
            )
            cleanup_thread.start()
            _safe_log_info('Started cleanup daemon thread')
        except Exception:
            _safe_log_exception('Failed to start cleanup thread')
    
    # Start palety monitor thread
    try:
        monitor_thread = threading.Thread(
            target=_monitor_unconfirmed_palety,
            kwargs={'threshold_minutes': 10, 'interval_seconds': 60},
            daemon=True
        )
        monitor_thread.start()
        _safe_log_info('Started palety monitor daemon thread')
    except Exception:
        _safe_log_exception('Failed to start palety monitor thread')

    # Start periodic refresh of bufor/Workowanie sync to keep DB in sync with Zasyp
    try:
        from app.db import refresh_bufor_queue

        def _periodic_refresh(interval_seconds=60):
            while True:
                try:
                    refresh_bufor_queue()
                    app.logger.debug('Periodic refresh_bufor_queue executed')
                except Exception:
                    app.logger.exception('Periodic refresh_bufor_queue failed')
                time.sleep(interval_seconds)

        refresh_thread = threading.Thread(
            target=_periodic_refresh,
            kwargs={'interval_seconds': 300},
            daemon=True
        )
        refresh_thread.start()
        _safe_log_info('Started periodic refresh_bufor_queue thread')
    except Exception:
        _safe_log_exception('Failed to start periodic refresh_bufor_queue thread')

    # Start hourly database backup thread
    try:
        backup_thread = threading.Thread(
            target=_backup_database,
            kwargs={'interval_seconds': 3600},
            daemon=True
        )
        backup_thread.start()
        _safe_log_info('Started database backup daemon thread')
    except Exception:
        _safe_log_exception('Failed to start database backup thread')


def _backup_database(interval_seconds=3600, keep_days=7):
    """Background thread: creates a MySQL dump every `interval_seconds` seconds.

    Connects to DB_HOST (192.168.0.18 by default) using credentials from app config.
    Saves compressed SQL dumps to the `backups/` directory.
    Purges backups older than `keep_days` days automatically.

    Args:
        interval_seconds: How often to run the backup (default: 3600 = 1h)
        keep_days: How many days of backups to retain (default: 7)
    """
    import subprocess
    import datetime
    from app.config import DB_CONFIG

    backup_dir = 'backups'

    while True:
        try:
            os.makedirs(backup_dir, exist_ok=True)

            now = datetime.datetime.now()
            filename = now.strftime('db-backup-%Y%m%d-%H%M%S.sql')
            filepath = os.path.join(backup_dir, filename)

            host = DB_CONFIG.get('host', '192.168.0.18')
            port = str(DB_CONFIG.get('port', 3306))
            user = DB_CONFIG.get('user', 'root')
            password = DB_CONFIG.get('password', '')
            database = DB_CONFIG.get('database', 'raportprodukcyjny')

            cmd = [
                'mysqldump',
                f'--host={host}',
                f'--port={port}',
                f'--user={user}',
                f'--password={password}',
                '--single-transaction',
                '--routines',
                '--triggers',
                '--skip-lock-tables',
                database
            ]

            with open(filepath, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=120
                )

            if result.returncode == 0:
                size_kb = os.path.getsize(filepath) // 1024
                _safe_log_info('DB backup created: %s (%d KB)', filepath, size_kb)
            else:
                err = result.stderr.decode('utf-8', errors='replace')
                _safe_log_warning('DB backup failed (code %d): %s', result.returncode, err[:200])
                try:
                    os.remove(filepath)
                except Exception:
                    pass

            # Purge backups older than keep_days
            cutoff = now.timestamp() - keep_days * 86400
            for name in os.listdir(backup_dir):
                if not name.startswith('db-backup-') or not name.endswith('.sql'):
                    continue
                path = os.path.join(backup_dir, name)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        _safe_log_info('Purged old backup: %s', path)
                except Exception:
                    pass

        except Exception:
            _safe_log_exception('Error in database backup thread')

        time.sleep(interval_seconds)

