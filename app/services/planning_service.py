"""Production planning service for managing production plans."""

from datetime import date, datetime, timedelta
import sys
import traceback
from app.db import get_db_connection
from flask import current_app


class PlanningService:
    """Service for managing production plans (creation, deletion, status changes, resumption)."""

    @staticmethod
    def create_plan(data_planu, produkt, tonaz, sekcja, typ_produkcji='worki_zgrzewane_25', 
                   status='zaplanowane', wymaga_oplaty=False):
        """Create a new production plan.
        
        Args:
            data_planu: Plan date (YYYY-MM-DD or date object)
            produkt: Product name (required)
            tonaz: Tonnage (kg or units)
            sekcja: Section/department
            typ_produkcji: Production type
            status: Initial status (nieoplacone|zaplanowane)
            wymaga_oplaty: Whether payment is required
            
        Returns:
            Tuple (success: bool, message: str, plan_id: int or None)
        """
        try:
            if not produkt or not produkt.strip():
                return (False, 'Produkt jest wymagany.', None)
            
            if isinstance(data_planu, date):
                data_planu = data_planu.isoformat()
            
            try:
                tonaz = int(float(tonaz)) if tonaz else 0
            except Exception:
                tonaz = 0
            
            # Normalize sekcja case - always capitalize first letter
            if sekcja:
                sekcja = sekcja.strip()
                sekcja = sekcja[0].upper() + sekcja[1:].lower() if sekcja else 'Zasyp'
            else:
                sekcja = 'Zasyp'
            
            # Determine initial status
            if wymaga_oplaty:
                initial_status = 'nieoplacone'
            else:
                initial_status = status or 'zaplanowane'
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get next sequence number for the day
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1
            
            # Insert new plan
            cursor.execute("""
                INSERT INTO plan_produkcji 
                (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (data_planu, produkt, tonaz, initial_status, sekcja, nk, typ_produkcji, 0))
            
            plan_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan created: id={plan_id}, produkt={produkt}, data={data_planu}')
            return (True, f'Plan dla {produkt} dodany.', plan_id)
            
        except Exception as e:
            current_app.logger.exception('Error creating plan')
            return (False, f'Błąd przy dodawaniu planu: {str(e)}', None)

    @staticmethod
    def delete_plan(plan_id):
        """Hard delete a plan (remove completely from database).
        
        Args:
            plan_id: ID of plan to delete
            
        Returns:
            Tuple (success: bool, message: str)
        """
        print(f'\n[SERVICE-DELETE] delete_plan({plan_id}) START - HARD DELETE')
        try:
            print(f'[SERVICE-DELETE] Connecting to database...')
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if plan exists and its status
            print(f'[SERVICE-DELETE] Finding plan ID={plan_id}...')
            cursor.execute("SELECT status, produkt, sekcja FROM plan_produkcji WHERE id=%s", (plan_id,))
            res = cursor.fetchone()
            print(f'[SERVICE-DELETE] Result: {res}')

            if not res:
                print(f'[SERVICE-DELETE] Plan not found!')
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            # Be tolerant to mocked fetchone shapes in tests (sometimes only status is returned)
            status = res[0] if len(res) > 0 else None
            produkt = res[1] if len(res) > 1 else None
            sekcja = res[2] if len(res) > 2 else None
            print(f'[SERVICE-DELETE] Found plan: status={status}, produkt={produkt}, sekcja={sekcja}')
            
            # Cannot delete if in progress or completed
            if status in ['w toku', 'zakonczone']:
                print(f'[SERVICE-DELETE] Plan has protected status: {status}')
                conn.close()
                # Use ascii form 'zakonczone' to match test expectations
                return (False, 'Nie można usunąć zlecenia w toku lub zakonczone.')
            
            # Hard delete: DELETE FROM plan_produkcji
            print(f'[SERVICE-DELETE] Executing DELETE...')
            cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (plan_id,))
            print(f'[SERVICE-DELETE] DELETE finished, rowcount={cursor.rowcount}')

            # Jeśli kasujemy Zasyp, usuń też powiązane zlecenie Workowanie (które jeszcze nie startowało)
            # Zapobiega to powstawaniu osieroconych zleceń w kolejce produkcyjnej.
            linked_deleted = 0
            if sekcja and sekcja.lower() == 'zasyp':
                cursor.execute(
                    "DELETE FROM plan_produkcji WHERE zasyp_id=%s AND status='zaplanowane'",
                    (plan_id,)
                )
                linked_deleted = cursor.rowcount
                print(f'[SERVICE-DELETE] Cascade: removed {linked_deleted} linked Workowanie (zasyp_id={plan_id})')

            conn.commit()
            print(f'[SERVICE-DELETE] COMMIT success')
            conn.close()
            print(f'[SERVICE-DELETE] Connection closed')

            if linked_deleted > 0:
                current_app.logger.info(
                    f'Plan deleted (hard delete): id={plan_id}, produkt={produkt}, sekcja={sekcja}'
                    f' + {linked_deleted} linked Workowanie removed (zasyp_id cascade)'
                )
            else:
                current_app.logger.info(f'Plan deleted (hard delete): id={plan_id}, produkt={produkt}, sekcja={sekcja}')
            msg = f'Zlecenie {produkt or plan_id} zostało usunięte z planu.'
            print(f'[SERVICE-DELETE] Success: {msg}')
            return (True, msg)
            
        except Exception as e:
            print(f'[SERVICE-DELETE] EXCEPTION: {str(e)}')
            print(f'[SERVICE-DELETE] Exception type: {type(e).__name__}')
            import traceback
            print(f'[SERVICE-DELETE] Traceback: {traceback.format_exc()}')
            try:
                conn.rollback()
                print(f'[SERVICE-DELETE] ROLLBACK done')
            except Exception as rb_err:
                print(f'[SERVICE-DELETE] Rollback error: {rb_err}')
            current_app.logger.exception(f'Error deleting plan {plan_id}')
            return (False, f'Błąd przy usuwaniu: {str(e)}')

    @staticmethod
    def restore_plan(plan_id):
        """Restore (un-delete) a deleted plan.
        
        Args:
            plan_id: ID of plan to restore
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if plan exists and is deleted
            cursor.execute(
                "SELECT is_deleted, produkt, status FROM plan_produkcji WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()

            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            is_deleted = res[0] if len(res) > 0 else 0
            produkt = res[1] if len(res) > 1 else None
            if not is_deleted:  # is_deleted = 0
                conn.close()
                return (False, 'To zlecenie nie jest usunięte.')
            
            # Restore: set is_deleted=0, deleted_at=NULL
            cursor.execute(
                "UPDATE plan_produkcji SET is_deleted=0, deleted_at=NULL WHERE id=%s",
                (plan_id,)
            )
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan restored: id={plan_id}, produkt={produkt}')
            return (True, f'Zlecenie zostało przywrócone.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error restoring plan {plan_id}')
            return (False, f'Błąd przy przywracaniu: {str(e)}')

    @staticmethod
    def resume_plan(plan_id):
        """Resume a paused/zaplanowane plan (change status to 'w toku').
        
        Args:
            plan_id: ID of plan to resume
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get section of this plan
            cursor.execute(
                "SELECT sekcja, produkt FROM plan_produkcji WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()

            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            sekcja = res[0] if len(res) > 0 else None
            produkt = res[1] if len(res) > 1 else None
            
            # Set all other plans in this section to zaplanowane (pause them)
            cursor.execute(
                "UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'",
                (sekcja,)
            )
            
            # Set this plan to w toku (resume)
            cursor.execute(
                "UPDATE plan_produkcji SET status='w toku', real_stop=NULL WHERE id=%s",
                (plan_id,)
            )
            
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan resumed: id={plan_id}, sekcja={sekcja}, produkt={produkt}')
            return (True, 'Zlecenie ustawione na w toku.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error resuming plan {plan_id}')
            return (False, f'Błąd przy wznawianiu: {str(e)}')

    @staticmethod
    def change_status(plan_id, new_status):
        """Change plan status.
        
        Args:
            plan_id: ID of plan
            new_status: New status value
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current plan info
            cursor.execute(
                "SELECT status, produkt FROM plan_produkcji WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            
            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')
            
            old_status = res[0]
            produkt = res[1]
            
            # Update status
            cursor.execute(
                "UPDATE plan_produkcji SET status=%s WHERE id=%s",
                (new_status, plan_id)
            )
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan status changed: id={plan_id}, {old_status} -> {new_status}')
            return (True, f'Status dla {produkt} zmieniony na {new_status}.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error changing status for plan {plan_id}')
            return (False, f'Błąd przy zmianie statusu: {str(e)}')

    @staticmethod
    def get_plan_details(plan_id):
        """Get detailed information about a plan.
        
        Args:
            plan_id: ID of plan
            
        Returns:
            Dict with plan details or error key
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, data_planu, produkt, tonaz, status, sekcja, 
                       kolejnosc, typ_produkcji, tonaz_rzeczywisty, is_deleted
                FROM plan_produkcji
                WHERE id=%s
            """, (plan_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return {'error': 'Plan nie istnieje.'}
            
            return {
                'id': row[0],
                'data_planu': row[1],
                'produkt': row[2],
                'tonaz': row[3],
                'status': row[4],
                'sekcja': row[5],
                'kolejnosc': row[6],
                'typ_produkcji': row[7],
                'tonaz_rzeczywisty': row[8],
                'is_deleted': row[9]
            }
            
        except Exception as e:
            current_app.logger.exception(f'Error retrieving plan {plan_id}')
            return {'error': f'Błąd przy pobieraniu planu: {str(e)}'}

    @staticmethod
    def get_plans_for_date(data_planu, include_deleted=False):
        """Get all plans for a specific date.
        
        Args:
            data_planu: Date (YYYY-MM-DD or date object)
            include_deleted: Whether to include soft-deleted plans
            
        Returns:
            List of plans or empty list if error
        """
        try:
            if isinstance(data_planu, date):
                data_planu = data_planu.isoformat()
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if include_deleted:
                sql = """
                    SELECT id, produkt, tonaz, status, sekcja, kolejnosc, 
                           typ_produkcji, tonaz_rzeczywisty
                    FROM plan_produkcji
                    WHERE data_planu=%s
                    ORDER BY kolejnosc ASC
                """
            else:
                sql = """
                    SELECT id, produkt, tonaz, status, sekcja, kolejnosc,
                           typ_produkcji, tonaz_rzeczywisty
                    FROM plan_produkcji
                    WHERE data_planu=%s AND (is_deleted=0 OR is_deleted IS NULL)
                    ORDER BY kolejnosc ASC
                """
            
            cursor.execute(sql, (data_planu,))
            rows = cursor.fetchall()
            conn.close()
            
            plans = []
            for row in rows:
                plans.append({
                    'id': row[0],
                    'produkt': row[1],
                    'tonaz': row[2],
                    'status': row[3],
                    'sekcja': row[4],
                    'kolejnosc': row[5],
                    'typ_produkcji': row[6],
                    'tonaz_rzeczywisty': row[7]
                })
            
            return plans
            
        except Exception as e:
            current_app.logger.exception(f'Error retrieving plans for {data_planu}')
            return []

    @staticmethod
    @staticmethod
    def reschedule_plan(plan_id, nowa_data):
        """Move a plan to a different date. Also moves buffer entries if they exist.
        
        Args:
            plan_id: Plan ID to reschedule
            nowa_data: New date (YYYY-MM-DD or date object)
            
        Returns:
            (success: bool, message: str)
        """
        import sys
        from datetime import date
        
        print(f'\n[SERVICE-RESCHEDULE] reschedule_plan({plan_id}, {nowa_data}) START', file=sys.stderr, flush=True)
        try:
            # Convert both dates to ISO string format for safe comparison
            if hasattr(nowa_data, 'isoformat'):
                nowa_data_str = nowa_data.isoformat()
            else:
                nowa_data_str = str(nowa_data)
            
            print(f'[SERVICE-RESCHEDULE] Connecting to DB...', file=sys.stderr, flush=True)
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Validate plan exists and check status
            print(f'[SERVICE-RESCHEDULE] Fetching plan {plan_id}...', file=sys.stderr, flush=True)
            cursor.execute("SELECT status, data_planu, produkt, tonaz_rzeczywisty FROM plan_produkcji WHERE id=%s", (plan_id,))
            res = cursor.fetchone()
            print(f'[SERVICE-RESCHEDULE] Result: {res}', file=sys.stderr, flush=True)
            
            if not res:
                print(f'[SERVICE-RESCHEDULE] Plan not found!', file=sys.stderr, flush=True)
                return False, 'Plan nie istnieje.'
            
            status = res[0]
            stara_data = res[1]
            produkt = res[2]
            tonaz_rzeczywisty = res[3]
            
            # Convert date object to string for safe comparison
            if hasattr(stara_data, 'isoformat'):
                stara_data_str = stara_data.isoformat()
            else:
                stara_data_str = str(stara_data)
            
            print(f'[SERVICE-RESCHEDULE] Plan {plan_id}: status={status}, stara_data={stara_data_str}, produkt={produkt}, tonaz_rz={tonaz_rzeczywisty}', file=sys.stderr, flush=True)
            print(f'[SERVICE-RESCHEDULE] Moving from {stara_data_str} to {nowa_data_str}', file=sys.stderr, flush=True)
            
            # Only block if plan is currently being unpacked (w toku)
            if status == 'w toku':
                print(f'[SERVICE-RESCHEDULE] Plan is w toku - cannot reschedule!', file=sys.stderr, flush=True)
                return False, 'Nie można przesunąć planu, który jest w rozpakowania (w toku).'
            
            # Get max sequence for target date
            print(f'[SERVICE-RESCHEDULE] Fetching max sequence for target date {nowa_data_str}...', file=sys.stderr, flush=True)
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (nowa_data_str,))
            max_seq = cursor.fetchone()
            nowa_kolejnosc = (max_seq[0] if max_seq and max_seq[0] else 0) + 1
            print(f'[SERVICE-RESCHEDULE] New sequence: {nowa_kolejnosc}', file=sys.stderr, flush=True)
            
            # Update date and reset sequence FOR PLAN
            print(f'[SERVICE-RESCHEDULE] Updating plan_produkcji: id={plan_id}, nowa_data={nowa_data_str}...', file=sys.stderr, flush=True)
            cursor.execute(
                "UPDATE plan_produkcji SET data_planu=%s, kolejnosc=%s WHERE id=%s",
                (nowa_data_str, nowa_kolejnosc, plan_id)
            )
            print(f'[SERVICE-RESCHEDULE] UPDATE plan_produkcji rowcount: {cursor.rowcount}', file=sys.stderr, flush=True)
            
            # NOW HANDLE BUFFER ENTRIES
            # Look for all active buffer entries by zasyp_id (no date restriction —
            # carry-over buffers may be on a different date than the plan itself)
            print(f'[SERVICE-RESCHEDULE] === BUFFER LOOKUP === Checking for buffer entries: zasyp_id={plan_id}', file=sys.stderr, flush=True)
            cursor.execute("""
                SELECT id, tonaz_rzeczywisty, spakowano, produkt, typ_produkcji
                FROM bufor
                WHERE zasyp_id=%s AND status='aktywny'
            """, (plan_id,))
            
            buffer_entries = cursor.fetchall()
            print(f'[SERVICE-RESCHEDULE] === BUFFER RESULT === Found {len(buffer_entries)} buffer entries', file=sys.stderr, flush=True)
            
            if buffer_entries:
                print(f'[SERVICE-RESCHEDULE] Found buffer entries! Moving them...', file=sys.stderr, flush=True)
                
                # Get max kolejka for target date in buffer
                cursor.execute(
                    "SELECT MAX(kolejka) FROM bufor WHERE data_planu=%s",
                    (nowa_data_str,)
                )
                max_buf_seq = cursor.fetchone()
                next_buf_kolejka = (max_buf_seq[0] if max_buf_seq and max_buf_seq[0] else 0) + 1
                print(f'[SERVICE-RESCHEDULE] Buffer next kolejka: {next_buf_kolejka}', file=sys.stderr, flush=True)
                
                for buf_entry in buffer_entries:
                    buf_id = buf_entry[0]
                    tonaz_rz = buf_entry[1]
                    spakowano = buf_entry[2]
                    produkt_buf = buf_entry[3]
                    typ_prod = buf_entry[4]
                    
                    print(f'[SERVICE-RESCHEDULE] Moving buffer entry {buf_id}: {produkt_buf} ({tonaz_rz}kg) spakowano={spakowano}...', file=sys.stderr, flush=True)
                    
                    # Update buffer entry with new date and new kolejka
                    cursor.execute("""
                        UPDATE bufor
                        SET data_planu=%s, kolejka=%s
                        WHERE id=%s
                    """, (nowa_data_str, next_buf_kolejka, buf_id))
                    
                    print(f'[SERVICE-RESCHEDULE] Buffer entry {buf_id} updated: rowcount={cursor.rowcount}', file=sys.stderr, flush=True)
                    next_buf_kolejka += 1
                    
                    current_app.logger.critical(
                        f'[RESCHEDULE] ✓ Moved buffer entry {buf_id}: {produkt_buf} '
                        f'from {stara_data_str} to {nowa_data_str} with {tonaz_rz}kg spakowano={spakowano}'
                    )
            else:
                print(f'[SERVICE-RESCHEDULE] NO buffer entries found - plan has no buffer entries yet', file=sys.stderr, flush=True)
            
            # Commit ALL changes
            conn.commit()
            print(f'[SERVICE-RESCHEDULE] COMMIT done', file=sys.stderr, flush=True)
            conn.close()
            print(f'[SERVICE-RESCHEDULE] SUCCESS - Plan moved successfully\n', file=sys.stderr, flush=True)
            
            if buffer_entries:
                msg = f'Plan i bufor przesunięte na nową datę ({len(buffer_entries)} wpisów: {", ".join([str(e[3]) for e in buffer_entries])}).'
                current_app.logger.critical(f'[RESCHEDULE-SUCCESS] {msg}')
            else:
                msg = 'Plan przesunięty na nową datę (bez wpisów w buforze).'
            
            return True, msg
            
        except Exception as e:
            print(f'[SERVICE-RESCHEDULE] *** EXCEPTION: {str(e)}', file=sys.stderr, flush=True)
            print(f'[SERVICE-RESCHEDULE] Traceback: {traceback.format_exc()}', file=sys.stderr, flush=True)
            current_app.logger.exception(f'Error rescheduling plan {plan_id}')
            try:
                conn.rollback()
                print(f'[SERVICE-RESCHEDULE] ROLLBACK done', file=sys.stderr, flush=True)
            except Exception as rb_err:
                print(f'[SERVICE-RESCHEDULE] ROLLBACK error: {rb_err}', file=sys.stderr, flush=True)
            return False, 'Błąd przy przesuwaniu planu.'

    @staticmethod
    def validate_and_fix_anomalies():
        """
        Find and fix anomalies: plans with tonaz_rzeczywisty > 0 but status='zaplanowane'.
        These were likely entered manually without proper status update.
        
        Returns:
            Tuple (success: bool, message: str, count: int) - count of fixed anomalies
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Find anomalies: tonaz_rzeczywisty > 0 but status = 'zaplanowane' and no real_start
            cursor.execute("""
                SELECT id, produkt, status, tonaz_rzeczywisty, real_start, real_stop
                FROM plan_produkcji
                WHERE status='zaplanowane' AND COALESCE(tonaz_rzeczywisty, 0) > 0 AND real_start IS NULL
                ORDER BY data_planu DESC
            """)
            
            anomalies = cursor.fetchall()
            fixed_count = 0
            
            if anomalies:
                current_app.logger.warning(f'Found {len(anomalies)} anomalies to fix')
                
                for anomaly in anomalies:
                    plan_id = anomaly['id']
                    produkt = anomaly['produkt']
                    tonaz_rz = anomaly['tonaz_rzeczywisty']
                    
                    try:
                        # Fix: Set status to 'zakonczone' since tonaz_rzeczywisty is already set
                        # (likely manually entered without proper workflow)
                        cursor.execute("""
                            UPDATE plan_produkcji 
                            SET status='zakonczone', 
                                real_start=IFNULL(real_start, NOW()),
                                real_stop=IFNULL(real_stop, NOW())
                            WHERE id=%s
                        """, (plan_id,))
                        
                        fixed_count += 1
                        current_app.logger.info(
                            f'Fixed anomaly: ID={plan_id}, {produkt} '
                            f'(tonaz_rz={tonaz_rz}kg, status: zaplanowane->zakonczone)'
                        )
                    except Exception as e:
                        current_app.logger.error(
                            f'✗ Failed to fix anomaly ID={plan_id}: {str(e)}'
                        )
                        conn.rollback()
                        continue
                
                conn.commit()
            
            conn.close()
            
            message = f'Naprawiono {fixed_count} anomalii' if fixed_count > 0 else 'Nie znaleziono anomalii'
            return (True, message, fixed_count)
            
        except Exception as e:
            current_app.logger.exception(f'Error validating anomalies: {str(e)}')
            return (False, f'Błąd przy sprawdzaniu anomalii: {str(e)}', 0)

    @staticmethod
    def ensure_status_after_tonaz_update(plan_id):
        """
        After tonaz_rzeczywisty is updated, ensure status reflects actual execution.
        If tonaz_rzeczywisty > 0 and status='zaplanowane', change to 'w toku'.
        
        Args:
            plan_id: Plan ID to validate
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Check current state
            cursor.execute("""
                SELECT id, status, tonaz_rzeczywisty, real_start, real_stop
                FROM plan_produkcji
                WHERE id=%s
            """, (plan_id,))
            
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return (False, 'Plan nie istnieje.')
            
            status = result['status']
            tonaz_rz = result['tonaz_rzeczywisty'] or 0
            real_start = result['real_start']
            real_stop = result['real_stop']
            
            # Logic: If tonaz_rzeczywisty > 0 but status is still 'zaplanowane'
            # and no real_start, update to 'w toku'
            if tonaz_rz > 0 and status == 'zaplanowane' and not real_start:
                cursor.execute("""
                    UPDATE plan_produkcji
                    SET status='w toku', real_start=NOW()
                    WHERE id=%s
                """, (plan_id,))
                
                conn.commit()
                current_app.logger.info(
                    f'Auto-corrected plan {plan_id}: status zaplanowane->w toku '
                    f'(tonaz_rzeczywisty={tonaz_rz})'
                )
                return (True, f'Status automatycznie zmieniony na "w toku" (tonaz={tonaz_rz}kg)')
            
            conn.close()
            return (True, 'Plan jest spójny')
            
        except Exception as e:
            current_app.logger.exception(f'Error ensuring status for plan {plan_id}: {str(e)}')
            return (False, f'Błąd przy sprawdzaniu statusu: {str(e)}')
    @staticmethod
    def przenies_niezrealizowane(current_data, plan_ids_to_move=None):
        """
        Move incomplete work to next day.

        Decision basis — BUFFER (remaining to pack), not Zasyp shortfall alone:
          1. If Workowanie packed less than was zasypane → create Workowanie carryover for next day.
             A companion "ghost" Zasyp plan (already done) is created so that refresh_bufor_queue
             can auto-populate the buffer with the correct remaining amount.
          2. If Zasyp itself didn't meet its plan → also create a new Zasyp plan for next day
             (+ empty Workowanie linked to it).

        Buffer entries for the current day are NOT deleted — they persist as history.

        Args:
            current_data: Date string (YYYY-MM-DD)
            plan_ids_to_move: Optional list of Zasyp plan IDs to process (None = all)

        Returns:
            Tuple (success: bool, message: str, count: int)
        """
        try:
            try:
                current_date = datetime.strptime(current_data, '%Y-%m-%d').date()
            except Exception as e:
                return (False, f'Nieprawidłowy format daty: {str(e)}', 0)

            next_date = current_date + timedelta(days=1)
            next_data_str = next_date.isoformat()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Fetch all closed Zasyp plans for the date, with their paired Workowanie plan
            if plan_ids_to_move:
                placeholders = ','.join(['%s'] * len(plan_ids_to_move))
                cursor.execute(f"""
                    SELECT z.id AS zasyp_id, z.produkt, z.typ_produkcji,
                           COALESCE(z.tonaz, 0) AS z_plan,
                           COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,
                           w.id AS workowanie_id,
                           COALESCE(w.tonaz, 0) AS w_plan,
                           COALESCE(w.tonaz_rzeczywisty, 0) AS w_real
                    FROM plan_produkcji z
                    LEFT JOIN plan_produkcji w
                        ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'
                    WHERE DATE(z.data_planu) = %s
                      AND z.status = 'zakonczone'
                      AND LOWER(z.sekcja) = 'zasyp'
                      AND z.id IN ({placeholders})
                    ORDER BY z.id
                """, [current_data] + list(plan_ids_to_move))
            else:
                cursor.execute("""
                    SELECT z.id AS zasyp_id, z.produkt, z.typ_produkcji,
                           COALESCE(z.tonaz, 0) AS z_plan,
                           COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,
                           w.id AS workowanie_id,
                           COALESCE(w.tonaz, 0) AS w_plan,
                           COALESCE(w.tonaz_rzeczywisty, 0) AS w_real
                    FROM plan_produkcji z
                    LEFT JOIN plan_produkcji w
                        ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'
                    WHERE DATE(z.data_planu) = %s
                      AND z.status = 'zakonczone'
                      AND LOWER(z.sekcja) = 'zasyp'
                    ORDER BY z.id
                """, (current_data,))

            plans = cursor.fetchall()
            update_cursor = conn.cursor()
            created_count = 0

            for plan in plans:
                zasyp_id = plan['zasyp_id']
                produkt = plan['produkt']
                typ_prod = plan['typ_produkcji'] or 'worki_zgrzewane_25'
                z_plan = plan['z_plan']
                z_real = plan['z_real']
                w_plan = plan['w_plan']
                w_real = plan['w_real']

                # Rule 1: remaining to pack = what Zasyp produced minus what was already packed
                # If no Workowanie plan exists, all zasypane goods need packing
                if plan['workowanie_id'] is not None:
                    workowanie_remaining = max(0.0, w_plan - w_real)
                else:
                    workowanie_remaining = max(0.0, z_real)

                # Rule 2: Zasyp shortfall = how much Zasyp still needs to do
                zasyp_remaining = max(0.0, z_plan - z_real)

                if workowanie_remaining <= 0 and zasyp_remaining <= 0:
                    continue

                # --- Rule 1: Workowanie carryover ---
                if workowanie_remaining > 0:
                    # Check for duplicate on next_date (same produkt + workowanie + zaplanowane)
                    cursor.execute("""
                        SELECT id FROM plan_produkcji
                        WHERE DATE(data_planu) = %s AND produkt = %s
                          AND LOWER(sekcja) = 'workowanie' AND status = 'zaplanowane'
                          AND zasyp_id IN (
                              SELECT id FROM plan_produkcji
                              WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'zasyp' AND status = 'zakonczone'
                                AND tonaz_rzeczywisty = %s
                          )
                    """, (next_data_str, produkt, next_data_str, workowanie_remaining))
                    if cursor.fetchone():
                        current_app.logger.info(
                            f'[PRZENIES] Carryover Workowanie already exists for {produkt} on {next_data_str}, skipping'
                        )
                    else:
                        # Create "ghost" Zasyp carryover directly (goods physically in buffer already)
                        # Use direct INSERT on outer conn so typ_zlecenia is set atomically — no
                        # separate UPDATE needed.  typ_zlecenia='carry_over_ghost' hides this record
                        # from the planista Zasyp view.
                        update_cursor.execute(
                            "SELECT COALESCE(MAX(kolejnosc), 0) FROM plan_produkcji WHERE data_planu = %s",
                            (next_data_str,)
                        )
                        nk_ghost = update_cursor.fetchone()[0] + 1
                        update_cursor.execute("""
                            INSERT INTO plan_produkcji
                            (data_planu, produkt, tonaz, status, sekcja, kolejnosc,
                             typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia)
                            VALUES (%s, %s, %s, 'zakonczone', 'Zasyp', %s,
                                    %s, %s, %s, 'carry_over_ghost')
                        """, (next_data_str, produkt, workowanie_remaining, nk_ghost,
                              typ_prod, workowanie_remaining,
                              f'[carry-over z {current_data}]'))
                        ghost_zasyp_id = update_cursor.lastrowid
                        if ghost_zasyp_id:
                            # Create Workowanie plan for packing
                            s_w, _, new_work_id = PlanningService.create_plan(
                                data_planu=next_data_str,
                                produkt=produkt,
                                tonaz=workowanie_remaining,
                                sekcja='Workowanie',
                                typ_produkcji=typ_prod,
                                status='zaplanowane'
                            )
                            if s_w and new_work_id:
                                update_cursor.execute(
                                    "UPDATE plan_produkcji SET zasyp_id = %s WHERE id = %s",
                                    (ghost_zasyp_id, new_work_id)
                                )
                                conn.commit()
                                created_count += 2
                                current_app.logger.info(
                                    f'[PRZENIES] Workowanie carryover: {produkt} {workowanie_remaining}kg'
                                    f' -> Zasyp ghost #{ghost_zasyp_id}, Workowanie #{new_work_id}'
                                )

                                # --- CRITICAL FIX: insert bufor entry directly ---
                                # refresh_bufor_queue only covers yesterday-today range, so the ghost
                                # Zasyp on next_date would never be added to bufor by the daemon until
                                # the server date catches up. We insert it here to make Workowanie
                                # immediately startable from the queue.
                                update_cursor.execute(
                                    "SELECT COALESCE(MAX(kolejka), 0) FROM bufor"
                                    " WHERE data_planu = %s AND status = 'aktywny'",
                                    (next_data_str,)
                                )
                                max_kol = update_cursor.fetchone()[0]
                                update_cursor.execute("""
                                    INSERT INTO bufor
                                    (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji,
                                     tonaz_rzeczywisty, spakowano, kolejka, status)
                                    VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny')
                                    ON DUPLICATE KEY UPDATE id = id
                                """, (ghost_zasyp_id, next_data_str, produkt,
                                      f'carry-over z {current_data}', typ_prod,
                                      workowanie_remaining, max_kol + 1))
                                conn.commit()
                                current_app.logger.info(
                                    f'[PRZENIES] Bufor entry inserted for {produkt} on {next_data_str}'
                                    f' (kolejka {max_kol + 1})'
                                )

                # --- Rule 2: Zasyp shortfall ---
                if zasyp_remaining > 0:
                    # Check for duplicate Zasyp shortfall on next_date
                    cursor.execute("""
                        SELECT id FROM plan_produkcji
                        WHERE DATE(data_planu) = %s AND produkt = %s
                          AND LOWER(sekcja) = 'zasyp' AND status = 'zaplanowane'
                    """, (next_data_str, produkt))
                    if cursor.fetchone():
                        current_app.logger.info(
                            f'[PRZENIES] Zasyp shortfall plan already exists for {produkt} on {next_data_str}, skipping'
                        )
                    else:
                        s_z2, _, new_zasyp_id = PlanningService.create_plan(
                            data_planu=next_data_str,
                            produkt=produkt,
                            tonaz=zasyp_remaining,
                            sekcja='Zasyp',
                            typ_produkcji=typ_prod,
                            status='zaplanowane'
                        )
                        if s_z2 and new_zasyp_id:
                            # Companion empty Workowanie plan (tonaz will be synced by refresh_bufor_queue)
                            s_w2, _, new_work2_id = PlanningService.create_plan(
                                data_planu=next_data_str,
                                produkt=produkt,
                                tonaz=0,
                                sekcja='Workowanie',
                                typ_produkcji=typ_prod,
                                status='zaplanowane'
                            )
                            if s_w2 and new_work2_id:
                                update_cursor.execute(
                                    "UPDATE plan_produkcji SET zasyp_id = %s WHERE id = %s",
                                    (new_zasyp_id, new_work2_id)
                                )
                                conn.commit()
                                created_count += 2
                                current_app.logger.info(
                                    f'[PRZENIES] Zasyp shortfall: {produkt} {zasyp_remaining}kg'
                                    f' -> Zasyp #{new_zasyp_id}, Workowanie #{new_work2_id}'
                                )

            update_cursor.close()
            conn.close()

            if created_count == 0:
                return (True, 'Brak planów do przeniesienia na następny dzień.', 0)

            product_count = created_count // 2
            message = (
                f'✓ Przeniesiono na {next_date.strftime("%d.%m.%Y")}: '
                f'{product_count} produktów ({created_count} planów)'
            )
            current_app.logger.info(f'[PRZENIES] {message}')
            return (True, message, created_count)

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error in przenies_niezrealizowane: {str(e)}')
            return (False, f'Błąd serwera: {str(e)}', 0)