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
    """Return maximum number of pallets to recover after a counter jump."""
    raw_value = os.getenv('AGRO_AUTO_PALLET_MAX_CATCHUP', '4')
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        _safe_log_warning(
            "Invalid AGRO_AUTO_PALLET_MAX_CATCHUP=%r. Falling back to 4.",
            raw_value,
        )
        return 4
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

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GET_LOCK(%s, %s)", (str(lock_name), int(timeout_seconds)))
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
        cursor = conn.cursor()
        cursor.execute("SELECT RELEASE_LOCK(%s)", (str(lock_name),))
    except Exception as lock_err:
        _safe_log_warning('Failed to release named lock %s: %s', lock_name, lock_err)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _select_preferred_printer(cursor):
    """Pick production printer first, then fallback to any active printer."""
    cursor.execute(
        """
        SELECT id, nazwa, ip, lokalizacja
        FROM drukarki
        WHERE aktywna = 1
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                ELSE 2
            END,
            id ASC
        LIMIT 1
        """
    )
    return cursor.fetchone()


def _print_wrapped_pallet_label_once(plan_id, last_printed_pallet_ids, linia='AGRO'):
    """On wrap rising edge print exactly one label for the newest pallet of active plan."""
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
                                cursor.execute("UPDATE print_jobs SET status='DONE', updated_at=NOW() WHERE id=%s", (job_id,))
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
                finally:
                    conn.close()
            except Exception as error:
                if not _is_transient_db_connectivity_error(error):
                    _safe_log_exception('Error in Print Spooler monitor loop')
            
            time.sleep(interval_seconds)
    except Exception:
        _safe_log_exception('Print Spooler monitor terminating unexpectedly')


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
                kwargs={'folder': reports_folder, 'max_age_hours': 24, 'interval_seconds': 3600},
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
            leader_lock_name = 'agro_pallet_daemon_leader'
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
                        
                        # Get latest telemetry
                        data = get_latest_data()
                        current_pallet_cnt = data.get('pallet_counter', 0)
                        current_wrapped = bool(data.get('is_wrapped'))
                        heartbeat_note = f'plan={plan_id};counter={current_pallet_cnt};wrapped={int(current_wrapped)}'

                        if current_pallet_cnt > 0:
                            # If we haven't tracked this plan yet, initialize it
                            if plan_id not in plan_counters:
                                # Self-healing: if start_pallet_counter in database is 0, update it
                                if not active_plan.get('start_pallet_counter'):
                                    try:
                                        from app.db import get_db_connection
                                        conn = get_db_connection()
                                        cursor = conn.cursor()
                                        cursor.execute(
                                            "UPDATE plan_produkcji_agro SET start_pallet_counter = %s WHERE id = %s",
                                            (current_pallet_cnt, plan_id)
                                        )
                                        conn.commit()
                                        conn.close()
                                        _safe_log_info("Initialized start_pallet_counter to %s for plan ID=%s", current_pallet_cnt, plan_id)
                                    except Exception as db_err:
                                        _safe_log_warning("Failed to initialize start_pallet_counter: %s", db_err)
                                
                                plan_counters[plan_id] = current_pallet_cnt
                                _safe_log_info(
                                    "Tracking palletizer counter for plan ID=%s. Initial value: %s (instance=%s)",
                                    plan_id,
                                    current_pallet_cnt,
                                    _INSTANCE_ID,
                                )
                            
                            # Detect increment
                            last_cnt = plan_counters[plan_id]
                            current_oproznianie = bool(data.get('oproznianie'))
                            
                            oproznianie_snap = data.get('oproznianie_snapshot')
                            recent_oproznianie = False
                            if oproznianie_snap and oproznianie_snap.get('timestamp'):
                                snap_ts = oproznianie_snap.get('timestamp')
                                if (time.time() * 1000 - snap_ts) < 90000:  # 90 seconds
                                    recent_oproznianie = True

                            if current_pallet_cnt > last_cnt and (current_oproznianie or recent_oproznianie):
                                _safe_log_warning(
                                    "Opróżnianie aktywne lub niedawne. Ignorowanie sygnału wyjazdu z paletyzatora (licznika) dla plan ID=%s. Przesuwanie bazy na %s.",
                                    plan_id,
                                    current_pallet_cnt,
                                )
                                plan_counters[plan_id] = current_pallet_cnt
                                continue

                            action = _resolve_pallet_counter_action(last_cnt, current_pallet_cnt)

                            if action == 'reset':
                                _safe_log_warning(
                                    "Palletizer counter moved backwards from %s to %s for plan ID=%s. Resyncing baseline without auto-register.",
                                    last_cnt,
                                    current_pallet_cnt,
                                    plan_id,
                                )
                                plan_counters[plan_id] = current_pallet_cnt
                            elif action in ('register_single', 'jump'):
                                diff = current_pallet_cnt - last_cnt
                                max_catchup = _get_auto_pallet_max_catchup()
                                registrations_to_run = _resolve_pallet_counter_registrations(
                                    last_cnt,
                                    current_pallet_cnt,
                                    max_catchup,
                                )

                                if registrations_to_run <= 0:
                                    _safe_log_warning(
                                        "Palletizer counter changed from %s to %s (diff=%s) for plan ID=%s but no registrations were resolved. Keeping baseline unchanged for retry (instance=%s).",
                                        last_cnt,
                                        current_pallet_cnt,
                                        diff,
                                        plan_id,
                                        _INSTANCE_ID,
                                    )
                                    plan_counters[plan_id] = last_cnt
                                    continue

                                if action == 'register_single':
                                    _safe_log_info(
                                        "Palletizer counter incremented from %s to %s (diff=%s) for plan ID=%s. Triggering single auto-pallet registration (instance=%s).",
                                        last_cnt,
                                        current_pallet_cnt,
                                        diff,
                                        plan_id,
                                        _INSTANCE_ID,
                                    )
                                else:
                                    _safe_log_warning(
                                        "Palletizer counter jump detected from %s to %s (diff=%s) for plan ID=%s. Running catch-up auto-register for %s pallets (limit=%s, instance=%s).",
                                        last_cnt,
                                        current_pallet_cnt,
                                        diff,
                                        plan_id,
                                        registrations_to_run,
                                        max_catchup,
                                        _INSTANCE_ID,
                                    )

                                successful_regs = 0
                                for step_idx in range(1, registrations_to_run + 1):
                                    success = AgroTanksService.auto_register_pallet(
                                        plan_id,
                                        linia='AGRO',
                                        source_instance=_INSTANCE_ID,
                                    )
                                    if not success:
                                        _safe_log_warning(
                                            'Failed or skipped auto-registering pallet for plan ID=%s during step %s/%s (instance=%s)',
                                            plan_id,
                                            step_idx,
                                            registrations_to_run,
                                            _INSTANCE_ID,
                                        )
                                        break
                                    successful_regs += 1

                                if successful_regs > 0:
                                    _safe_log_info(
                                        'Auto-registered %s/%s pallet(s) for plan ID=%s (instance=%s)',
                                        successful_regs,
                                        registrations_to_run,
                                        plan_id,
                                        _INSTANCE_ID,
                                    )

                                # Advance only by successfully inserted pallets.
                                # This keeps remaining counter increments pending for next loop,
                                # including jumps bigger than the per-loop catch-up limit.
                                plan_counters[plan_id] = last_cnt + successful_regs

                                if plan_counters[plan_id] < current_pallet_cnt:
                                    _safe_log_warning(
                                        'Counter baseline partially advanced to %s for plan ID=%s (target counter=%s, remaining=%s, instance=%s).',
                                        plan_counters[plan_id],
                                        plan_id,
                                        current_pallet_cnt,
                                        current_pallet_cnt - plan_counters[plan_id],
                                        _INSTANCE_ID,
                                    )
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

    _safe_log_info('Periodic refresh_bufor_queue thread disabled (event-driven mode)')
