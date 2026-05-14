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


def _midnight_order_closer(interval_seconds=60):
    """Background thread: at 00:00, closes all unclosed orders from previous days with stop time 15:00."""
    from app.db import get_db_connection
    from datetime import datetime, date
    
    _safe_log_info('Midnight Order Closer thread started')
    
    last_run_date = None
    
    while True:
        try:
            now = datetime.now()
            # Check if it's midnight and we haven't run today yet
            if now.hour == 0 and now.minute == 0 and last_run_date != now.date():
                today_str = now.strftime('%Y-%m-%d')
                _safe_log_info('Starting midnight order cleanup for date %s', today_str)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Close orders for both lines that are overdue (data_planu < today)
                # Set real_stop to 15:00:00 of that plan date
                for table in ['plan_produkcji', 'plan_produkcji_agro']:
                    cursor.execute(f"""
                        UPDATE {table} 
                        SET status = 'zakonczone', 
                            real_stop = CONCAT(data_planu, ' 15:00:00')
                        WHERE status NOT IN ('zakonczone', 'anulowane')
                          AND data_planu < %s
                    """, (now.date(),))
                    
                    if cursor.rowcount > 0:
                        _safe_log_info('Auto-closed %s orders in %s', cursor.rowcount, table)
                
                conn.commit()
                conn.close()
                
                last_run_date = now.date()
                _safe_log_info('Midnight cleanup completed')
                
        except Exception:
            _safe_log_exception('Error in midnight order closer loop')
            
        time.sleep(interval_seconds)


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

    # Start midnight closer thread
    try:
        closer_thread = threading.Thread(
            target=_midnight_order_closer,
            kwargs={'interval_seconds': 60},
            daemon=True
        )
        closer_thread.start()
        _safe_log_info('Started midnight order closer daemon thread')
    except Exception:
        _safe_log_exception('Failed to start midnight closer thread')

    # Bufor jest odświeżany zdarzeniowo (start Zasypu), nie periodicznie.
    # Periodyczny wątek wyłączony celowo — unikamy błędnych wpięć do kolejki
    # zanim zlecenie faktycznie pojawi się na zasypie.
    _safe_log_info('Periodic refresh_bufor_queue thread disabled (event-driven mode)')

