"""Background daemon threads for maintenance tasks."""

import os
import socket
import time
import threading
from datetime import datetime, timedelta
from flask import current_app
from app.services.mqtt_service import start_mqtt_bridge

# Global set to track reminded palety to avoid duplicate log entries
_reminded_palety = set()

# Global logger for palety-specific events
palety_logger = None
_last_unconfirmed_db_error_log_at = 0.0

_INSTANCE_HOSTNAME = socket.gethostname() or 'unknown-host'
_INSTANCE_PID = os.getpid()
_INSTANCE_STARTED_TS = int(time.time())
_INSTANCE_STARTED_AT = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(_INSTANCE_STARTED_TS))
_INSTANCE_ID = f"{_INSTANCE_HOSTNAME}:{_INSTANCE_PID}:{_INSTANCE_STARTED_TS}"


def _resolve_pallet_counter_action(last_cnt, current_cnt):
    """Decide how auto-register should react to pallet counter movement.

    Returns one of: 'none', 'register_single', 'jump', 'reset'.
    """
    if current_cnt < last_cnt:
        return 'reset'
    if current_cnt == last_cnt:
        return 'none'
    if (current_cnt - last_cnt) == 1:
        return 'register_single'
    return 'jump'


def _get_auto_pallet_max_catchup():
    """Return maximum number of pallets to recover after a counter jump.
    Defaults to 1 to prevent burst duplicate auto-pallets on packaging lines.
    """
    raw_value = os.getenv('AGRO_AUTO_PALLET_MAX_CATCHUP', '1')
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        _safe_log_warning(
            "Invalid AGRO_AUTO_PALLET_MAX_CATCHUP=%r. Falling back to 1.",
            raw_value,
        )
        return 1
    return max(1, parsed)


def _resolve_pallet_counter_registrations(last_cnt, current_cnt, max_catchup):
    """Return number of pallets to register for current movement."""
    action = _resolve_pallet_counter_action(last_cnt, current_cnt)
    if action == 'register_single':
        return 1
    if action == 'jump':
        diff = current_cnt - last_cnt
        return min(diff, max_catchup)
    return 0


def get_instance_identity():
    """Return runtime identity for diagnosing multi-instance behavior."""
    return {
        'instance_id': _INSTANCE_ID,
        'hostname': _INSTANCE_HOSTNAME,
        'pid': _INSTANCE_PID,
        'started_at': _INSTANCE_STARTED_AT,
    }


def _is_rising_edge(previous_state, current_state):
    """True only on False -> True transitions."""
    return (not bool(previous_state)) and bool(current_state)


def _ensure_instance_heartbeat_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_instance_heartbeat (
            instance_id VARCHAR(128) PRIMARY KEY,
            hostname VARCHAR(128) NOT NULL,
            pid INT NOT NULL,
            component VARCHAR(64) NOT NULL,
            status VARCHAR(64) NOT NULL,
            started_at DATETIME NOT NULL,
            last_heartbeat DATETIME NOT NULL,
            extra VARCHAR(255) NULL,
            INDEX idx_component_heartbeat (component, last_heartbeat)
        )
        """
    )


def _update_instance_heartbeat(component, status='running', extra=''):
    """Upsert daemon heartbeat so we can spot duplicated running instances."""
    from app.db import get_db_connection

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_instance_heartbeat_table(cursor)
        cursor.execute(
            """
            INSERT INTO app_instance_heartbeat
                (instance_id, hostname, pid, component, status, started_at, last_heartbeat, extra)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                last_heartbeat = VALUES(last_heartbeat),
                extra = VALUES(extra)
            """,
            (
                _INSTANCE_ID,
                _INSTANCE_HOSTNAME,
                _INSTANCE_PID,
                component,
                status,
                _INSTANCE_STARTED_AT,
                str(extra or '')[:255],
            ),
        )
        conn.commit()
    except Exception as hb_err:
        _safe_log_warning('Failed to update instance heartbeat: %s', hb_err)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _acquire_named_lock(lock_name, timeout_seconds=0):
    """Try to acquire a MySQL named lock and keep it by holding the connection."""
    from app.db import get_db_connection
    from app.core.database import get_active_database_name

    conn = None
    try:
        active_db = get_active_database_name() or 'default'
        scoped_lock = f"{lock_name}_{active_db}"
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GET_LOCK(%s, %s)", (str(scoped_lock), int(timeout_seconds)))
        row = cursor.fetchone()
        acquired = bool(row and int(row[0]) == 1)
        if acquired:
            return conn
    except Exception as lock_err:
        _safe_log_warning('Failed to acquire named lock %s: %s', lock_name, lock_err)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    return None


def _release_named_lock(conn, lock_name):
    """Release a MySQL named lock and close its connection safely."""
    if not conn:
        return

    try:
        from app.core.database import get_active_database_name
        active_db = get_active_database_name() or 'default'
        scoped_lock = f"{lock_name}_{active_db}"
        cursor = conn.cursor()
        cursor.execute("SELECT RELEASE_LOCK(%s)", (str(scoped_lock),))
    except Exception as lock_err:
        _safe_log_warning('Failed to release named lock %s: %s', lock_name, lock_err)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _select_preferred_printer(cursor, linia='AGRO'):
    """Pobiera preferowaną aktywną drukarkę z bazy danych dla danej linii."""
    try:
        from app.repositories.settings_repository import SettingsRepository
        return SettingsRepository.get_default_printer_for_line(linia)
    except Exception:
        cursor.execute(
            """
            SELECT id, nazwa, ip, lokalizacja
            FROM drukarki
            WHERE aktywna = 1
            ORDER BY id ASC
            LIMIT 1
            """
        )
        return cursor.fetchone()


def _print_wrapped_pallet_label_once(plan_id, last_printed_pallet_ids, linia='AGRO'):
    """On wrap rising edge print exactly one label for the newest pallet of active plan."""
    # Automated printing after wrapper is disabled upon user request
    return False, 'Automatyczny wydruk po owijarce został wyłączony', None

    from app.db import get_db_connection, get_table_name
    from app.services.print_server import get_printer

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)

        cursor.execute(
            f"""
            SELECT pw.id, pw.nr_palety, pw.waga, pw.data_dodania, p.produkt
            FROM {table_pal} pw
            JOIN {table_plan} p ON p.id = pw.plan_id
            WHERE pw.plan_id = %s
            ORDER BY pw.id DESC
            LIMIT 1
            """,
            (plan_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False, 'Brak palety do wydruku po sygnale owijarki', None

        pallet_id = int(row['id'])
        if last_printed_pallet_ids.get(plan_id) == pallet_id:
            return False, 'Duplikat sygnału owijarki - paleta już wydrukowana', pallet_id

        printer_row = _select_preferred_printer(cursor)
        printer = get_printer()

        from app.utils.pallet_label import prepare_pallet_label_data
        label_data = prepare_pallet_label_data(cursor, pallet_id, linia, source_table='workowanie')
        if not label_data:
            return False, 'Nie udało się przygotować danych etykiety', pallet_id

        label_data['uwagi'] = f"wrap_edge instance={_INSTANCE_ID}"

        override_ip = printer_row.get('ip') if printer_row else None
        override_name = printer_row.get('nazwa') if printer_row else None
        ok, msg = printer.print_finished_product_label(
            label_data,
            override_ip=override_ip,
            override_name=override_name,
        )
        if ok:
            last_printed_pallet_ids[plan_id] = pallet_id
        return ok, msg, pallet_id
    except Exception as print_err:
        return False, f'Błąd triggera owijarki: {print_err}', None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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


def _iter_exception_chain(error):
    current = error
    seen_ids = set()
    while current is not None and id(current) not in seen_ids:
        seen_ids.add(id(current))
        yield current
        current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)


def _is_transient_db_connectivity_error(error):
    tokens = (
        'unknown mysql server host',
        'can\'t connect to mysql server',
        'cannot connect to mysql server',
        'lost connection to mysql server',
        'name or service not known',
        'temporary failure in name resolution',
        'connection refused',
        '(11001)',
        '(2005',
        '(2003',
    )
    for chained_error in _iter_exception_chain(error):
        message = str(chained_error or '').lower()
        if any(token in message for token in tokens):
            return True
    return False


def _cleanup_old_files(folder, max_age_hours=24, interval_seconds=3600, pattern="*"):
    """Background thread: removes files in `folder` matching `pattern` older than `max_age_hours`.
    
    Args:
        folder: Directory to clean up
        max_age_hours: Maximum age in hours before removal
        interval_seconds: How often to run cleanup check
        pattern: Optional pattern to filter files (not used for now, cleans all files in folder)
    """
    try:
        while True:
            try:
                if os.path.exists(folder):
                    now = time.time()
                    max_age = max_age_hours * 3600
                    count = 0
                    for name in os.listdir(folder):
                        path = os.path.join(folder, name)
                        try:
                            if os.path.isfile(path):
                                mtime = os.path.getmtime(path)
                                if now - mtime > max_age:
                                    try:
                                        os.remove(path)
                                        count += 1
                                    except Exception:
                                        _safe_log_exception('Failed to remove file: %s', path)
                        except Exception:
                            _safe_log_exception('Error checking file: %s', path)
                    if count > 0:
                        _safe_log_info('Cleanup [%s]: Removed %d old files (older than %dh)', folder, count, max_age_hours)
            except Exception:
                _safe_log_exception('Error in cleanup loop for %s', folder)
            time.sleep(interval_seconds)
    except Exception:
        _safe_log_exception('Cleanup thread for %s terminating unexpectedly', folder)

def _ensure_midnight_production_database():
    """At midnight, force runtime DB back to production if test DB is active."""
    from app.db import get_active_database_name, set_active_database_name

    active_db = get_active_database_name()
    if active_db == 'biblioteka_testowa':
        set_active_database_name('biblioteka', verify_connection=True)
        _safe_log_warning(
            'Midnight DB guard: switched active database from %s to biblioteka.',
            active_db,
        )

def _midnight_order_closer(interval_seconds=60):
    """Background thread: at 00:00, closes all unclosed orders from previous days with stop time 15:00."""
    from app.db import get_db_connection
    from datetime import datetime, date, timedelta
    
    _safe_log_info('Midnight Order Closer thread started')
    
    last_run_date = None
    
    while True:
        try:
            now = datetime.now()
            # Check if it's midnight and we haven't run today yet
            if now.hour == 0 and now.minute == 0 and last_run_date != now.date():
                today_str = now.strftime('%Y-%m-%d')

                _ensure_midnight_production_database()
                _safe_log_info('Starting midnight order cleanup for date %s', today_str)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
                
                # Close PSD orders that are overdue
                cursor.execute("""
                    UPDATE plan_produkcji 
                    SET status = 'zakonczone', 
                        real_stop = CONCAT(data_planu, ' 15:00:00')
                    WHERE status = 'w toku'
                      AND data_planu < %s
                """, (now.date(),))
                
                if cursor.rowcount > 0:
                    _safe_log_info('Auto-closed %s orders in plan_produkcji', cursor.rowcount)
                
                # Suspend AGRO orders that are overdue instead of closing them
                cursor.execute("""
                    UPDATE plan_produkcji_agro 
                    SET status = 'zawieszone', 
                        czas_pracy_sekundy = czas_pracy_sekundy + TIMESTAMPDIFF(SECOND, COALESCE(ostatnie_wznowienie, CONCAT(%s, ' 07:00:00')), CONCAT(%s, ' 15:00:00'))
                    WHERE status = 'w toku'
                      AND data_planu < %s
                """, (yesterday_str, yesterday_str, now.date()))
                
                if cursor.rowcount > 0:
                    _safe_log_info('Auto-suspended %s orders in plan_produkcji_agro', cursor.rowcount)
                
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
    
    global _last_unconfirmed_db_error_log_at

    try:
        while True:
            try:
                conn = None
                cursor = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.waga = 0 AND COALESCE(pw.status,'') <> 'przyjeta' AND TIMESTAMPDIFF(MINUTE, pw.data_dodania, NOW()) >= %s",
                        (threshold_minutes,)
                    )
                    raw_rows = cursor.fetchall()
                finally:
                    try:
                        if cursor:
                            cursor.close()
                    except Exception:
                        pass
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

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
            except Exception as error:
                if _is_transient_db_connectivity_error(error):
                    now_ts = time.monotonic()
                    if (now_ts - _last_unconfirmed_db_error_log_at) >= 300:
                        _safe_log_warning('Unconfirmed palety monitor: DB chwilowo niedostepna (%s). Kolejna proba za %ss.', error, interval_seconds)
                        _last_unconfirmed_db_error_log_at = now_ts
                else:
                    _safe_log_exception('Error in unconfirmed palety monitor loop')
            time.sleep(interval_seconds)
    except Exception:
        _safe_log_exception('Unconfirmed palety monitor terminating unexpectedly')

def _print_spooler_loop(interval_seconds: int = 5):
    """Monitoruje tabelę print_jobs i wysyła zakolejkowane wydruki w tle."""
    try:
        from app.db import get_db_connection
        from app.services.print_server import PrintServer
        printer = PrintServer()

        _safe_log_info(f'Started Print Spooler daemon thread, interval {interval_seconds}s')
        while True:
            try:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor(dictionary=True)
                    
                    # Ensure only one worker processes the print queue
                    cursor.execute("SELECT GET_LOCK('print_spooler_daemon_leader', 0)")
                    lock_result = cursor.fetchone()
                    got_lock = list(lock_result.values())[0] if lock_result else 0
                    
                    if not got_lock:
                        continue

                    # Szukamy zadań PENDING lub ERROR z liczbą prób < 3
                    cursor.execute("""
                        SELECT id, printer_ip, printer_name, zpl_content, retry_count
                        FROM print_jobs 
                        WHERE status = 'PENDING' OR (status = 'ERROR' AND retry_count < 3)
                        ORDER BY id ASC LIMIT 5
                    """)
                    jobs = cursor.fetchall()

                    for job in jobs:
                        job_id = job['id']
                        zpl = job['zpl_content']
                        ip = job['printer_ip']
                        name = job['printer_name']
                        retry = job['retry_count']

                        # Ustawiamy status na PRINTING
                        cursor.execute("UPDATE print_jobs SET status='PRINTING' WHERE id=%s", (job_id,))
                        conn.commit()

                        try:
                            # Wysyłka do mostka
                            payload = {"drukarka": name, "ip": ip, "dane": zpl}
                            success, msg = printer._send_to_bridge(payload)
                            
                            if success:
                                curr_cnt = 0
                                new_cnt = 1
                                try:
                                    cursor.execute("SELECT id, licznik_wydrukow FROM drukarki WHERE ip = %s OR nazwa = %s LIMIT 1", (ip, name))
                                    pr_row = cursor.fetchone()
                                    if pr_row:
                                        curr_cnt = int(pr_row.get('licznik_wydrukow') or 0)
                                        new_cnt = curr_cnt + 1
                                        cursor.execute("UPDATE drukarki SET licznik_wydrukow = %s WHERE id = %s", (new_cnt, pr_row['id']))
                                except Exception:
                                    try:
                                        cursor.execute("ALTER TABLE drukarki ADD COLUMN licznik_wydrukow INT DEFAULT 0")
                                        new_cnt = 1
                                    except Exception:
                                        pass

                                log_note = f"Czujniki ~HS OK | Licznik drukarki: {curr_cnt} ➔ {new_cnt}"
                                cursor.execute("UPDATE print_jobs SET status='DONE', error_message=%s, updated_at=NOW() WHERE id=%s", (log_note, job_id))
                            else:
                                cursor.execute("UPDATE print_jobs SET status='ERROR', error_message=%s, retry_count=%s, updated_at=NOW() WHERE id=%s", 
                                               (msg, retry + 1, job_id))
                            conn.commit()
                        except Exception as e:
                            import traceback
                            err = f"{e}\n{traceback.format_exc()}"
                            cursor.execute("UPDATE print_jobs SET status='ERROR', error_message=%s, retry_count=%s, updated_at=NOW() WHERE id=%s", 
                                           (err, retry + 1, job_id))
                            conn.commit()
                            
                    if got_lock:
                        cursor.execute("SELECT RELEASE_LOCK('print_spooler_daemon_leader')")
                finally:
                    conn.close()
            except Exception as error:
                if not _is_transient_db_connectivity_error(error):
                    _safe_log_exception('Error in Print Spooler monitor loop')
            
            time.sleep(interval_seconds)
    except Exception:
        _safe_log_exception('Print Spooler monitor terminating unexpectedly')

def _cleanup_old_print_jobs(max_age_days: int = 14, interval_seconds: int = 86400):
    """Background thread: removes completed (DONE) print jobs older than max_age_days."""
    try:
        from app.db import get_db_connection
        _safe_log_info(f'Started Print Jobs Cleanup daemon thread (retention: {max_age_days}d)')
        while True:
            try:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        DELETE FROM print_jobs 
                        WHERE status = 'DONE' 
                          AND updated_at < NOW() - INTERVAL %s DAY
                    """, (max_age_days,))
                    deleted_count = cursor.rowcount
                    conn.commit()
                    if deleted_count > 0:
                        _safe_log_info('Cleanup [print_jobs]: Usunięto %d zakończonych zleceń druku starszych niż %dd', deleted_count, max_age_days)
                finally:
                    conn.close()
            except Exception as error:
                if not _is_transient_db_connectivity_error(error):
                    _safe_log_exception('Error in Print Jobs cleanup loop')
            time.sleep(interval_seconds)
    except Exception:
        _safe_log_exception('Print Jobs cleanup thread terminating unexpectedly')


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
    
    # Start cleanup threads
    if cleanup_enabled:
        try:
            # 1. Clean old reports
            reports_folder = os.path.join(app.root_path, 'raporty')
            if not os.path.exists(reports_folder):
                reports_folder = os.path.join(os.path.dirname(app.root_path), 'raporty')
                
            reports_thread = threading.Thread(
                target=_cleanup_old_files,
                kwargs={'folder': reports_folder, 'max_age_hours': 24 * 90, 'interval_seconds': 3600},
                daemon=True
            )
            reports_thread.start()
            
            # 2. Clean old sounds (TTS)
            # Find static sounds folder
            static_sounds = os.path.join(app.root_path, 'static', 'sounds')
            if not os.path.exists(static_sounds):
                static_sounds = os.path.join(os.path.dirname(app.root_path), 'static', 'sounds')
                
            sounds_thread = threading.Thread(
                target=_cleanup_old_files,
                kwargs={'folder': static_sounds, 'max_age_hours': 24, 'interval_seconds': 3600},
                daemon=True
            )
            sounds_thread.start()
            
            _safe_log_info('Started cleanup daemon threads (reports & sounds)')
        except Exception:
            _safe_log_exception('Failed to start cleanup threads')
    
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

    # Start Print Spooler thread
    try:
        spooler_thread = threading.Thread(
            target=_print_spooler_loop,
            kwargs={'interval_seconds': 5},
            daemon=True
        )
        spooler_thread.start()
        _safe_log_info('Started Print Spooler daemon thread')
    except Exception:
        _safe_log_exception('Failed to start Print Spooler thread')

    # Start Print Jobs Cleanup thread
    try:
        cleanup_jobs_thread = threading.Thread(
            target=_cleanup_old_print_jobs,
            kwargs={'max_age_days': 14, 'interval_seconds': 86400},
            daemon=True
        )
        cleanup_jobs_thread.start()
        _safe_log_info('Started Print Jobs Cleanup daemon thread')
    except Exception:
        _safe_log_exception('Failed to start Print Jobs cleanup thread')

    # Start MQTT Cloud Bridge (Server-side proxy)
    try:
        start_mqtt_bridge()
    except Exception:
        _safe_log_exception('Failed to start MQTT bridge')

    # Start AGRO Pallet Auto-Register thread
    try:
        from app.services.mqtt_service import get_latest_data
        from app.services.agro.agro_tanks_service import AgroTanksService
        
        def _agro_pallet_auto_register_loop():
            _safe_log_info(
                'AGRO Pallet Auto-Register thread started (using Palletizer counter, instance=%s)',
                _INSTANCE_ID,
            )
            time.sleep(15) # Safety delay to let app initialize
            
            # Map plan_id -> last_seen_counter
            plan_counters = {}
            # Map plan_id -> previous wrapped bit value
            plan_wrap_states = {}
            # Map plan_id -> last pallet id printed by wrap rising edge
            last_printed_wrap_pallet_ids = {}
            next_heartbeat_at = 0.0
            leader_lock_name = 'agro_pallet_daemon_leader_v2'
            leader_lock_conn = None
            next_lock_retry_at = 0.0
            
            while True:
                daemon_status = 'running'
                heartbeat_note = 'idle'

                # Only one process should execute AGRO auto-register logic at a time.
                # If lock is busy, stay in standby and only publish heartbeat.
                if not leader_lock_conn:
                    now_ts = time.time()
                    if now_ts >= next_lock_retry_at:
                        leader_lock_conn = _acquire_named_lock(leader_lock_name, timeout_seconds=0)
                        next_lock_retry_at = now_ts + 2.0
                        if leader_lock_conn:
                            _safe_log_info(
                                'AGRO daemon became lock leader (lock=%s, instance=%s).',
                                leader_lock_name,
                                _INSTANCE_ID,
                            )

                    if not leader_lock_conn:
                        daemon_status = 'standby'
                        heartbeat_note = 'standby:leader_lock_busy'
                        if now_ts >= next_heartbeat_at:
                            _update_instance_heartbeat(
                                component='agro_pallet_daemon',
                                status=daemon_status,
                                extra=heartbeat_note,
                            )
                            next_heartbeat_at = now_ts + 15
                        time.sleep(1.0)
                        continue
                else:
                    try:
                        leader_lock_conn.ping(reconnect=False, attempts=1, delay=0)
                    except Exception:
                        _safe_log_warning(
                            'Lost AGRO daemon leader lock connection. Switching to standby and retrying lock (instance=%s).',
                            _INSTANCE_ID,
                        )
                        _release_named_lock(leader_lock_conn, leader_lock_name)
                        leader_lock_conn = None
                        daemon_status = 'standby'
                        heartbeat_note = 'standby:leader_lock_lost'
                        now_ts = time.time()
                        if now_ts >= next_heartbeat_at:
                            _update_instance_heartbeat(
                                component='agro_pallet_daemon',
                                status=daemon_status,
                                extra=heartbeat_note,
                            )
                            next_heartbeat_at = now_ts + 15
                        time.sleep(1.0)
                        continue

                try:
                    active_plan = AgroTanksService.get_active_workowanie_plan(linia='AGRO')
                    if active_plan:
                        plan_id = active_plan['id']
                        
                        # Pobranie najnowszych danych telemetrycznych
                        data = get_latest_data()
                        pakowaczka_counter = data.get('counter', 0)
                        local_bag_counter = data.get('local_counter', 0)
                        palletizer_cnt = data.get('pallet_counter', 0)
                        bpm = data.get('bpm', 0.0)
                        mach_status = data.get('status')
                        current_wrapped = bool(data.get('is_wrapped'))
                        
                        # Określenie liczby worków na 1 pełną paletę (1000 kg)
                        typ_prod = str(active_plan.get('typ_produkcji') or '').lower()
                        if '20' in typ_prod:
                            bags_per_pallet = 50
                        elif '50' in typ_prod:
                            bags_per_pallet = 20
                        else:
                            bags_per_pallet = 40

                        heartbeat_note = f'plan={plan_id};pakowaczka={pakowaczka_counter};paletyzator={palletizer_cnt};bpm={bpm}'

                        # Inicjalizacja licznika początkowego paletyzatora w bazie jeśli nie ustawiony
                        start_pallet_cnt = active_plan.get('start_pallet_counter')
                        if palletizer_cnt > 0 and (not start_pallet_cnt or int(start_pallet_cnt) <= 0):
                            try:
                                from app.db import get_db_connection
                                conn_init = get_db_connection()
                                cur_init = conn_init.cursor()
                                cur_init.execute(
                                    "UPDATE plan_produkcji_agro SET start_pallet_counter = %s WHERE id = %s",
                                    (palletizer_cnt, plan_id)
                                )
                                conn_init.commit()
                                conn_init.close()
                                start_pallet_cnt = palletizer_cnt
                                active_plan['start_pallet_counter'] = palletizer_cnt
                                _safe_log_info("Initialized start_pallet_counter to %s for plan ID=%s", palletizer_cnt, plan_id)
                            except Exception as init_err:
                                _safe_log_warning("Failed to initialize start_pallet_counter: %s", init_err)
                                start_pallet_cnt = palletizer_cnt

                        # Inicjalizacja licznika początkowego pakowaczki w bazie jeśli nie ustawiony (do statystyk i folii)
                        start_machine_cnt = active_plan.get('start_machine_counter')
                        if pakowaczka_counter > 0 and (not start_machine_cnt or int(start_machine_cnt) <= 0):
                            try:
                                from app.db import get_db_connection
                                conn_init = get_db_connection()
                                cur_init = conn_init.cursor()
                                cur_init.execute(
                                    "UPDATE plan_produkcji_agro SET start_machine_counter = %s WHERE id = %s",
                                    (pakowaczka_counter, plan_id)
                                )
                                conn_init.commit()
                                conn_init.close()
                                start_machine_cnt = pakowaczka_counter
                                active_plan['start_machine_counter'] = pakowaczka_counter
                                _safe_log_info("Initialized start_machine_counter to %s for plan ID=%s", pakowaczka_counter, plan_id)
                            except Exception as init_err:
                                _safe_log_warning("Failed to initialize start_machine_counter: %s", init_err)
                                start_machine_cnt = pakowaczka_counter

                        # Obliczenie ile pełnych palet ukończył paletyzator (po zjechaniu pełnej palety w dół z windy)
                        completed_pallets = max(0, palletizer_cnt - int(start_pallet_cnt or 0)) if (palletizer_cnt > 0 and int(start_pallet_cnt or 0) > 0) else 0
                        bags_produced = max(0, pakowaczka_counter - int(start_machine_cnt or 0)) if (pakowaczka_counter > 0 and int(start_machine_cnt or 0) > 0) else 0

                        # Pobranie aktualnej liczby zarejestrowanych palet oraz obecności palety z opróżniania
                        db_pallets_count = 0
                        has_emptying_pallet = False
                        try:
                            from app.core.database import get_db_connection
                            conn_cnt = get_db_connection()
                            cur_cnt = conn_cnt.cursor()
                            cur_cnt.execute(
                                "SELECT COUNT(*), "
                                "SUM(CASE WHEN (waga < 1000 OR (dodal_login IS NOT NULL AND dodal_login != 'System')) THEN 1 ELSE 0 END) "
                                "FROM palety_agro WHERE plan_id = %s AND (status IS NULL OR status != 'rezerwacja')",
                                (plan_id,)
                            )
                            row_cnt = cur_cnt.fetchone()
                            if row_cnt:
                                db_pallets_count = int(row_cnt[0] or 0)
                                has_emptying_pallet = bool(row_cnt[1] and row_cnt[1] > 0)
                            conn_cnt.close()
                        except Exception as db_cnt_err:
                            _safe_log_warning("Failed to query db_pallets_count: %s", db_cnt_err)

                        is_emptying_now = bool(data.get('oproznianie') or data.get('is_emptying'))
                        last_empty_ts = float(data.get('last_oproznianie_ts') or 0)
                        is_in_emptying_mode = is_emptying_now or ((time.time() - last_empty_ts) < 300 if last_empty_ts > 0 else False) or has_emptying_pallet

                        # Sprawdzenie czy paletyzator ukończył nową pełną paletę (zjazd z windy)
                        if palletizer_cnt > 0 and int(start_pallet_cnt or 0) > 0 and completed_pallets > db_pallets_count:
                            if is_in_emptying_mode:
                                _safe_log_info(
                                    "Paletyzator zjechał z windą podczas/po opróżnianiu (oproznianie=%s, delta=%.1fs, has_emptying_pallet=%s). "
                                    "Licznik: %s (start: %s, w bazie: %s). "
                                    "Zablokowano dodanie automatycznej palety 1000kg. Priorytet ma opróżnianie - oczekiwanie na wpisanie wagi przez operatora w oknie.",
                                    is_emptying_now,
                                    time.time() - last_empty_ts if last_empty_ts else 0,
                                    has_emptying_pallet,
                                    palletizer_cnt,
                                    start_pallet_cnt,
                                    db_pallets_count,
                                )
                            else:
                                _safe_log_info(
                                    "Paletyzator zjechał z windą w dół i ukończył paletę! Licznik palet: %s (start: %s, ukończonych: %s, w bazie: %s). Rejestracja palety #%s.",
                                    palletizer_cnt,
                                    start_pallet_cnt,
                                    completed_pallets,
                                    db_pallets_count,
                                    db_pallets_count + 1,
                                )
                                
                                success = AgroTanksService.auto_register_pallet(
                                    plan_id,
                                    linia='AGRO',
                                    source_instance=_INSTANCE_ID,
                                )
                                if success:
                                    _safe_log_info(
                                        'Pomyślnie zarejestrowano paletę #%s na podstawie zjazdu z windy paletyzatora (instance=%s)',
                                        db_pallets_count + 1,
                                        _INSTANCE_ID,
                                    )
                                else:
                                    _safe_log_warning(
                                        'Rejestracja palety na podstawie paletyzatora wstrzymana przez cooldown/pułapkę (instance=%s)',
                                        _INSTANCE_ID,
                                    )
                        else:
                            # Stan pracy paletyzatora / pakowaczki – rejestr diagnostyczny do pułapki sygnałów
                            try:
                                last_tracked_cnt = plan_counters.get(plan_id, 0)
                                last_tracked_pal = plan_counters.get(f"{plan_id}_pal", 0)
                                if pakowaczka_counter != last_tracked_cnt and (pakowaczka_counter % 10 == 0 or palletizer_cnt != last_tracked_pal):
                                    from app.services.pakowaczka_signal_trap_service import PakowaczkaSignalTrapService
                                    PakowaczkaSignalTrapService.log_signal(
                                        decision='TRACKING_PALETYZATOR',
                                        source_machine='PALETYZATOR',
                                        plan_id=plan_id,
                                        produkt=active_plan.get('produkt'),
                                        global_counter=pakowaczka_counter,
                                        local_counter=local_bag_counter,
                                        pallet_counter=palletizer_cnt,
                                        delta_counter=pakowaczka_counter - (last_tracked_cnt or pakowaczka_counter),
                                        bpm=bpm,
                                        status_text=mach_status,
                                        details=f"Paletyzator: {completed_pallets} palet ukończonych (start={start_pallet_cnt}, bieżący={palletizer_cnt}). Pakowaczka: {bags_produced} worków. Zarejestrowanych palet w bazie: {db_pallets_count}.",
                                        instance_id=_INSTANCE_ID,
                                    )
                            except Exception:
                                pass

                        plan_counters[plan_id] = pakowaczka_counter
                        plan_counters[f"{plan_id}_pal"] = palletizer_cnt
                        # Initialize wrapped baseline for new plans, then only print on False->True transitions.
                        if plan_id not in plan_wrap_states:
                            plan_wrap_states[plan_id] = current_wrapped
                            _safe_log_info(
                                'Tracking owijarka bit for plan ID=%s. Initial wrapped=%s (instance=%s)',
                                plan_id,
                                current_wrapped,
                                _INSTANCE_ID,
                            )
                        else:
                            prev_wrapped = plan_wrap_states.get(plan_id)
                            if _is_rising_edge(prev_wrapped, current_wrapped):
                                ok_print, wrap_msg, printed_pallet_id = _print_wrapped_pallet_label_once(
                                    plan_id,
                                    last_printed_wrap_pallet_ids,
                                    linia='AGRO',
                                )
                                if ok_print:
                                    _safe_log_info(
                                        'Wrap rising edge detected for plan ID=%s -> printed one label for pallet ID=%s (instance=%s).',
                                        plan_id,
                                        printed_pallet_id,
                                        _INSTANCE_ID,
                                    )
                                else:
                                    _safe_log_info(
                                        'Wrap rising edge detected for plan ID=%s but label print skipped: %s (instance=%s).',
                                        plan_id,
                                        wrap_msg,
                                        _INSTANCE_ID,
                                    )
                                heartbeat_note = f'{heartbeat_note};wrap_edge=1;print_ok={int(ok_print)};pallet_id={printed_pallet_id}'
                            plan_wrap_states[plan_id] = current_wrapped
                        
                    else:
                        # No active plan, clear counters map to release memory and allow reset
                        plan_counters.clear()
                        plan_wrap_states.clear()
                        last_printed_wrap_pallet_ids.clear()
                        heartbeat_note = 'idle:no_active_plan'
                except Exception:
                    _safe_log_exception('Error in AGRO pallet auto-register loop')
                    heartbeat_note = 'error:loop_exception'

                now_ts = time.time()
                if now_ts >= next_heartbeat_at:
                    _update_instance_heartbeat(
                        component='agro_pallet_daemon',
                        status=daemon_status,
                        extra=heartbeat_note,
                    )
                    next_heartbeat_at = now_ts + 15
                
                time.sleep(1.0) # Check every second (highly sufficient and responsive for counter changes)
                
        auto_reg_thread = threading.Thread(target=_agro_pallet_auto_register_loop, daemon=True)
        auto_reg_thread.start()
        _safe_log_info('Started AGRO pallet auto-register daemon thread')
    except Exception:
        _safe_log_exception('Failed to start AGRO pallet auto-register thread')

    # Start 15:00 / Dynamic Auto-Report Daemon Thread
    try:
        def _auto_report_scheduler_loop():
            _safe_log_info('Auto-report daemon loop started (target: dynamic shift 1 scheduled time)')
            leader_lock_name = 'auto_report_daemon_leader'
            leader_lock_conn = None
            next_lock_retry_at = 0.0

            while True:
                try:
                    # Zapewnij, że tylko jedna instancja/worker wykonuje harmonogram auto-raportów
                    if not leader_lock_conn:
                        now_ts = time.time()
                        if now_ts >= next_lock_retry_at:
                            leader_lock_conn = _acquire_named_lock(leader_lock_name, timeout_seconds=0)
                            next_lock_retry_at = now_ts + 5.0
                            if leader_lock_conn:
                                _safe_log_info('Auto-report daemon became lock leader (instance=%s)', _INSTANCE_ID)

                    if not leader_lock_conn:
                        time.sleep(5.0)
                        continue
                    else:
                        try:
                            leader_lock_conn.ping(reconnect=False, attempts=1, delay=0)
                        except Exception:
                            _release_named_lock(leader_lock_conn, leader_lock_name)
                            leader_lock_conn = None
                            time.sleep(2.0)
                            continue

                    now = datetime.now()
                    today_str = now.strftime('%Y-%m-%d')
                    now_time_str = now.strftime('%H:%M:%S')

                    from app.services.auto_report_service import AutoReportService
                    from datetime import timedelta

                    global_cfg = AutoReportService.get_global_config()
                    enabled_lines = global_cfg.get('enabled_lines', ['AGRO', 'PSD'])

                    # 1. Sprawdzanie bieżącego dnia (podstawowe okno wysyłki o 15:00 lub wg harmonogramu)
                    is_standard_report_day = AutoReportService.is_report_day(today_str)
                    for linia in ['AGRO', 'PSD']:
                        if linia not in enabled_lines:
                            continue

                        sched = AutoReportService.get_schedule(linia, today_str)
                        # Dzień jest aktywny, jeśli to standardowy dzień roboczy LUB lider ustawił indywidualny czas na dziś
                        if not is_standard_report_day and not sched.get('is_custom'):
                            continue

                        if not AutoReportService.is_1500_report_sent(linia, today_str):
                            if not sched.get('is_paused'):
                                sched_time = sched.get('scheduled_time_full') or '15:00:00'
                                if now_time_str >= sched_time:
                                    _safe_log_info(f'[AUTO_REPORT] Triggering report for {linia} on {today_str} (sched: {sched_time}, now: {now_time_str})')
                                    with app.app_context():
                                        success, msg = AutoReportService.send_shift1_report_at_1500(linia=linia, date_str=today_str)
                                        _safe_log_info(f'[AUTO_REPORT] Result for {linia} on {today_str}: success={success}, msg={msg}')

                    # 2. Sprawdzanie dziennego raportu zbiorczego z dostaw i przesunięć magazynowych
                    try:
                        from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
                        wh_cfg = OsipEmailSettingsRepository().get_settings()
                        if wh_cfg.is_active and wh_cfg.daily_report_enabled:
                            wh_sched_time = (wh_cfg.daily_report_time or '15:00').strip()
                            if len(wh_sched_time) == 5:
                                wh_sched_time += ':00'
                            
                            if now_time_str >= wh_sched_time and wh_cfg.last_daily_report_date != today_str:
                                _safe_log_info(f'[WAREHOUSE_DAILY_REPORT] Triggering daily report for {today_str} (sched: {wh_sched_time}, now: {now_time_str})')
                                with app.app_context():
                                    from app.services.osip_report_email_service import OsipReportEmailService
                                    success, msg = OsipReportEmailService().send_daily_warehouse_summary_report(date_str=today_str, force=False)
                                    _safe_log_info(f'[WAREHOUSE_DAILY_REPORT] Result for {today_str}: success={success}, msg={msg}')
                    except Exception as _whe:
                        _safe_log_exception(f'Error checking warehouse daily report: {_whe}')

                except Exception as _e:
                    _safe_log_exception(f'Error in auto-report scheduler loop: {_e}')
                
                time.sleep(10.0) # Check every 10 seconds

        report_thread = threading.Thread(target=_auto_report_scheduler_loop, daemon=True)
        report_thread.start()
        _safe_log_info('Started Dynamic Auto-Report daemon thread')
    except Exception:
        _safe_log_exception('Failed to start Auto-Report daemon thread')

    _safe_log_info('Periodic refresh_bufor_queue thread disabled (event-driven mode)')
