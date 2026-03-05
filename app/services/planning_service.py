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
        print(f'\n🔥 [SERVICE-1] delete_plan({plan_id}) START - HARD DELETE')
        try:
            print(f'🔥 [SERVICE-2] Łączę się z bazą...')
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if plan exists and its status
            print(f'🔥 [SERVICE-3] Szukam planu ID={plan_id}...')
            cursor.execute("SELECT status, produkt, sekcja FROM plan_produkcji WHERE id=%s", (plan_id,))
            res = cursor.fetchone()
            print(f'🔥 [SERVICE-4] Wynik SELECT: {res}')

            if not res:
                print(f'🔥 [SERVICE-5] Plan nie znaleziony!')
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            # Be tolerant to mocked fetchone shapes in tests (sometimes only status is returned)
            status = res[0] if len(res) > 0 else None
            produkt = res[1] if len(res) > 1 else None
            sekcja = res[2] if len(res) > 2 else None
            print(f'🔥 [SERVICE-6] Plan znaleziony: status={status}, produkt={produkt}, sekcja={sekcja}')
            
            # Cannot delete if in progress or completed
            if status in ['w toku', 'zakonczone']:
                print(f'🔥 [SERVICE-7] Plan ma status zabroniony do usunięcia: {status}')
                conn.close()
                # Use ascii form 'zakonczone' to match test expectations
                return (False, 'Nie można usunąć zlecenia w toku lub zakonczone.')
            
            # Hard delete: DELETE FROM plan_produkcji
            print(f'🔥 [SERVICE-8] Wykonuję DELETE...')
            cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (plan_id,))
            print(f'🔥 [SERVICE-9] DELETE zakończony, rowcount={cursor.rowcount}')

            # Jeśli kasujemy Zasyp, usuń też powiązane zlecenie Workowanie (które jeszcze nie startowało)
            # Zapobiega to powstawaniu osieroconych zleceń w kolejce produkcyjnej.
            linked_deleted = 0
            if sekcja and sekcja.lower() == 'zasyp':
                cursor.execute(
                    "DELETE FROM plan_produkcji WHERE zasyp_id=%s AND status='zaplanowane'",
                    (plan_id,)
                )
                linked_deleted = cursor.rowcount
                print(f'🔥 [SERVICE-9b] Kaskada: usunięto {linked_deleted} powiązanych zlecen Workowanie (zasyp_id={plan_id})')

            conn.commit()
            print(f'🔥 [SERVICE-10] COMMIT wykonany')
            conn.close()
            print(f'🔥 [SERVICE-11] Połączenie zamknięte')

            if linked_deleted > 0:
                current_app.logger.info(
                    f'Plan deleted (hard delete): id={plan_id}, produkt={produkt}, sekcja={sekcja}'
                    f' + {linked_deleted} linked Workowanie removed (zasyp_id cascade)'
                )
            else:
                current_app.logger.info(f'Plan deleted (hard delete): id={plan_id}, produkt={produkt}, sekcja={sekcja}')
            msg = f'Zlecenie {produkt or plan_id} zostało usunięte z planu.'
            print(f'🔥 [SERVICE-12] Zwracam sukces: {msg}')
            return (True, msg)
            
        except Exception as e:
            print(f'🔥 [SERVICE-13] EXCEPTION: {str(e)}')
            print(f'🔥 [SERVICE-14] Exception type: {type(e).__name__}')
            import traceback
            print(f'🔥 [SERVICE-15] Traceback: {traceback.format_exc()}')
            try:
                conn.rollback()
                print(f'🔥 [SERVICE-16] ROLLBACK wykonany')
            except Exception as rb_err:
                print(f'🔥 [SERVICE-17] Błąd rollback: {rb_err}')
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
    def reschedule_plan(plan_id, nowa_data):
        """Move a plan to a different date.
        
        Args:
            plan_id: Plan ID to reschedule
            nowa_data: New date (YYYY-MM-DD or date object)
            
        Returns:
            (success: bool, message: str)
        """
        print(f'\n📅 [SERVICE-1] reschedule_plan({plan_id}, {nowa_data}) START')
        try:
            print(f'📅 [SERVICE-2] Connecting to DB...')
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Validate plan exists and check status
            print(f'📅 [SERVICE-3] Fetching plan {plan_id}...')
            cursor.execute("SELECT status FROM plan_produkcji WHERE id=%s", (plan_id,))
            res = cursor.fetchone()
            print(f'📅 [SERVICE-4] Result: {res}')
            
            if not res:
                print(f'📅 [SERVICE-5] Plan not found!')
                return False, 'Plan nie istnieje.'
            
            status = res[0]
            print(f'📅 [SERVICE-6] Current status: {status}')
            
            # Only block if plan is currently being unpacked (w toku)
            # Allow reschedule for "zakonczone" (closed, ready to unpack) or other statuses
            if status == 'w toku':
                print(f'📅 [SERVICE-7] Plan is currently being unpacked - cannot reschedule!')
                return False, 'Nie można przesunąć planu, który jest rozpakowania (w toku).'
            
            # Get max sequence for target date
            print(f'📅 [SERVICE-8] Fetching max sequence for date {nowa_data}...')
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (nowa_data,))
            max_seq = cursor.fetchone()
            nowa_kolejnosc = (max_seq[0] if max_seq and max_seq[0] else 0) + 1
            print(f'📅 [SERVICE-9] New sequence: {nowa_kolejnosc}')
            
            # Update date and reset sequence
            print(f'📅 [SERVICE-10] Executing UPDATE...')
            cursor.execute(
                "UPDATE plan_produkcji SET data_planu=%s, kolejnosc=%s WHERE id=%s",
                (nowa_data, nowa_kolejnosc, plan_id)
            )
            print(f'📅 [SERVICE-11] UPDATE rowcount: {cursor.rowcount}')
            conn.commit()
            print(f'📅 [SERVICE-12] COMMIT done')
            conn.close()
            print(f'📅 [SERVICE-13] Connection closed - SUCCESS\n')
            return True, 'Plan przesunięte na nową datę.'
            
        except Exception as e:
            print(f'📅 [SERVICE-14] EXCEPTION: {str(e)}')
            print(f'📅 [SERVICE-15] Traceback: {traceback.format_exc()}')
            current_app.logger.exception(f'Error rescheduling plan {plan_id}')
            try:
                conn.rollback()
                print(f'📅 [SERVICE-16] ROLLBACK done')
            except Exception as rb_err:
                print(f'📅 [SERVICE-17] ROLLBACK error: {rb_err}')
                pass
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
                current_app.logger.warning(f'🔧 Found {len(anomalies)} anomalies to fix')
                
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
                            f'✓ Fixed anomaly: ID={plan_id}, {produkt} '
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
                    f'✓ Auto-corrected plan {plan_id}: status zaplanowane->w toku '
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
        Move incomplete plans to next day.
        Creates new Zasyp and Workowanie plans for incomplete work.
        Moves buffer entries to next day.
        
        Args:
            current_data: Date string (YYYY-MM-DD)
            plan_ids_to_move: Optional list of plan IDs to move (if None, moves all incomplete)
            
        Returns:
            Tuple (success: bool, message: str, count: int)
        """
        import sys
        try:
            # ULTRA DEBUG on stderr and file log
            print(f'[PRZENIES SERVICE] *** FUNCTION CALLED *** current_data={current_data}, plan_ids_to_move={plan_ids_to_move}', file=sys.stderr, flush=True)
            current_app.logger.critical(f'[PRZENIES SERVICE] *** FUNCTION CALLED *** current_data={current_data}, plan_ids_to_move={plan_ids_to_move}')
            current_app.logger.info(f'[PRZENIES SERVICE] START - received current_data={current_data} (type={type(current_data).__name__})')
            
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Validate date
            try:
                current_date = datetime.strptime(current_data, '%Y-%m-%d').date()
                current_app.logger.info(f'[PRZENIES SERVICE] Parsed current_date={current_date}, next_date will be={current_date + timedelta(days=1)}')
            except Exception as e:
                current_app.logger.error(f'[PRZENIES SERVICE] Date parse ERROR: {str(e)}')
                return (False, f'Nieprawidłowy format daty: {str(e)}')
            
            # Calculate next date (add 1 day)
            next_date = current_date + timedelta(days=1)
            next_data_str = next_date.isoformat()
            
            # Get all incomplete plans on current date (status 'zakonczone' but not fully executed)
            # Only Zasyp - is the source of work
            if plan_ids_to_move:
                # Move only selected plans
                placeholders = ','.join(['%s'] * len(plan_ids_to_move))
                cursor.execute(f"""
                    SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji
                    FROM plan_produkcji
                    WHERE DATE(data_planu) = %s AND status = 'zakonczone'
                      AND LOWER(sekcja) = 'zasyp'
                      AND id IN ({placeholders})
                      AND (tonaz_rzeczywisty IS NULL OR tonaz_rzeczywisty < tonaz)
                    ORDER BY id
                """, [current_data] + plan_ids_to_move)
            else:
                # Move all incomplete plans
                cursor.execute("""
                    SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji
                    FROM plan_produkcji
                    WHERE DATE(data_planu) = %s AND status = 'zakonczone'
                      AND LOWER(sekcja) = 'zasyp'
                      AND (tonaz_rzeczywisty IS NULL OR tonaz_rzeczywisty < tonaz)
                    ORDER BY id
                """, (current_data,))
            
            incomplete_plans = cursor.fetchall()
            plans_to_create = []
            
            # Process each incomplete Zasyp plan
            for plan in incomplete_plans:
                plan_id = plan['id']
                produkt = plan['produkt']
                plan_tonaz = plan['tonaz'] or 0
                real_tonaz = plan['tonaz_rzeczywisty'] or 0
                typ_prod = plan['typ_produkcji'] or 'worki_zgrzewane_25'
                
                # Calculate remaining
                remaining = plan_tonaz - real_tonaz
                
                print(f'[PRZENIES] DEBUG: plan_id={plan_id}, tonaz={plan_tonaz}, real_tonaz={real_tonaz}, remaining={remaining}', 
                      file=sys.stderr, flush=True)
                
                # Only create new plans if there's remaining work
                if remaining > 0:
                    # Create both Zasyp and Workowanie for this product
                    plans_to_create.append({
                        'sekcja': 'Zasyp',
                        'produkt': produkt,
                        'plan': remaining,  # 5905 kg - remaining to do in Zasyp
                        'real_tonaz': real_tonaz,  # 1095 kg - already done
                        'typ_produkcji': typ_prod,
                        'source_plan_id': plan_id
                    })
                    plans_to_create.append({
                        'sekcja': 'Workowanie',
                        'produkt': produkt,
                        'plan': real_tonaz,  # 1095 kg - what Zasyp already did (to pack)
                        'real_tonaz': real_tonaz,  # 1095 kg - for buffer
                        'typ_produkcji': typ_prod,
                        'source_plan_id': plan_id
                    })
                    print(f'[PRZENIES] ADDING BOTH PLANS: sekcja=Zasyp (plan={remaining}), sekcja=Workowanie (plan={real_tonaz}, real_tonaz={real_tonaz})', 
                          file=sys.stderr, flush=True)
            
            # Create new plans on next day and add Zasyp plans to buffer
            created_count = 0
            buffer_insert_count = 0
            buffer_insert_cursor = conn.cursor()
            
            for plan_data in plans_to_create:
                try:
                    print(f'[PRZENIES] PROCESSING PLAN DATA: sekcja={plan_data["sekcja"]}, produkt={plan_data["produkt"]}, plan={plan_data["plan"]}, real_tonaz={plan_data.get("real_tonaz", "MISSING")}',
                          file=sys.stderr, flush=True)
                    current_app.logger.info(
                        f'[PRZENIES LOOP] plan_data keys: {list(plan_data.keys())}, real_tonaz value: {plan_data.get("real_tonaz")}'
                    )
                    
                    success, msg, new_id = PlanningService.create_plan(
                        data_planu=next_data_str,
                        produkt=plan_data['produkt'],
                        tonaz=plan_data['plan'],
                        sekcja=plan_data['sekcja'],
                        typ_produkcji=plan_data['typ_produkcji'],
                        status='zaplanowane'
                    )
                    
                    if success:
                        created_count += 1
                        print(f'[PRZENIES SERVICE] ✓ CREATE_PLAN SUCCESS: new_id={new_id}, ={plan_data["sekcja"]}, produkt={plan_data["produkt"]}', 
                              file=sys.stderr, flush=True)
                        current_app.logger.critical(
                            f'[PRZENIES SERVICE] ✓ CREATE_PLAN SUCCESS: new_id={new_id}, sekcja={plan_data["sekcja"]}'
                        )
                        current_app.logger.info(
                            f'✓ Przeniesiono: {plan_data["produkt"]} ({plan_data["plan"]}kg) '
                            f'z planu {plan_data["source_plan_id"]} na {next_data_str}'
                        )
                        
                        # Check section FIRST (before using it)
                        sekcja_lower = plan_data['sekcja'].lower()
                        
                        # If this is a Zasyp plan, add it to buffer for next day
                        # Do this IMMEDIATELY after create, BEFORE updating tonaz_rzeczywisty
                        if sekcja_lower == 'zasyp':
                            try:
                                # Get next kolejka number for this date
                                buffer_insert_cursor.execute(
                                    "SELECT MAX(kolejka) FROM bufor WHERE data_planu = %s",
                                    (next_data_str,)
                                )
                                result = buffer_insert_cursor.fetchone()
                                next_kolejka = (result[0] if result and result[0] else 0) + 1
                                
                                # Use real_tonaz value from dict (what Zasyp already did)
                                real_tonaz_value = plan_data.get('real_tonaz')
                                if real_tonaz_value is None:
                                    real_tonaz_value = 0
                                
                                current_app.logger.critical(
                                    f'[PRZENIES BUFFER] About to insert to buffer: plan_id={new_id}, sekcja={plan_data["sekcja"]}, real_tonaz_value from dict={plan_data.get("real_tonaz")}, final_value={real_tonaz_value}'
                                )
                                
                                print(f'[PRZENIES SERVICE] *** BEFORE BUFFER INSERT *** plan_id={new_id}, data={next_data_str}, real_tonaz_value={real_tonaz_value}, kolejka={next_kolejka}', 
                                      file=sys.stderr, flush=True)
                                
                                # Insert into buffer with what Zasyp actually did (to be packed)
                                buffer_insert_cursor.execute("""
                                    INSERT INTO bufor 
                                    (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'aktywny')
                                """, (new_id, next_data_str, plan_data['produkt'], '', 
                                      plan_data['typ_produkcji'], real_tonaz_value, 0, next_kolejka))
                                
                                insert_rowcount = buffer_insert_cursor.rowcount
                                conn.commit()  # ← COMMITTING BUFFER INSERT!
                                print(f'[PRZENIES SERVICE] *** AFTER BUFFER INSERT + COMMIT (rowcount={insert_rowcount}) *** plan_id={new_id}', 
                                      file=sys.stderr, flush=True)
                                current_app.logger.critical(
                                    f'[PRZENIES SERVICE] BUFFER INSERT RESULT: new_id={new_id}, rowcount={insert_rowcount}'
                                )
                                
                                if insert_rowcount > 0:
                                    buffer_insert_count += 1
                                    current_app.logger.info(
                                        f'✓ Dodano do bufora: {plan_data["produkt"]} na {next_date.strftime("%Y-%m-%d")}'
                                    )
                                    print(f'[PRZENIES SERVICE] ✓ BUFFER INSERT: plan_id={new_id}, produkt={plan_data["produkt"]}, data={next_data_str}', 
                                          file=sys.stderr, flush=True)
                                else:
                                    current_app.logger.warning(f'Buffer insert failed for plan {new_id}')
                            except Exception as be:
                                current_app.logger.warning(
                                    f'Error adding plan {new_id} to buffer: {str(be)}'
                                )
                        
                        # NOW update newly created plan with tonaz_rzeczywisty
                        # NEW DAY = ALWAYS START WITH 0 EXECUTION
                        # Real tonnage (1095kg) goes to BUFFER, not to plan execution
                        tonaz_value = 0
                        cursor.execute(
                            "UPDATE plan_produkcji SET tonaz_rzeczywisty = %s WHERE id = %s",
                            (tonaz_value, new_id)
                        )
                        conn.commit()  # COMMIT immediately so daemon reads correct value
                        print(f'[PRZENIES SERVICE] ✓ UPDATE COMMITTED: plan_id={new_id}, sekcja={plan_data["sekcja"]}, tonaz_rzeczywisty={tonaz_value}',
                              file=sys.stderr, flush=True)
                    else:
                        current_app.logger.warning(f'Failed to create plan: {msg}')
                except Exception as e:
                    print(f'[PRZENIES SERVICE] *** EXCEPTION IN PLAN CREATION LOOP *** {str(e)}', file=sys.stderr, flush=True)
                    current_app.logger.critical(f'[PRZENIES SERVICE] *** EXCEPTION: {str(e)}')
                    current_app.logger.warning(f'Error creating plan for {plan_data["produkt"]}: {str(e)}')
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    continue
            
            # Commit buffer inserts IMMEDIATELY before any other operations
            try:
                print(f'[PRZENIES SERVICE] *** ABOUT TO COMMIT BUFFER INSERTS (count={buffer_insert_count}) ***', 
                      file=sys.stderr, flush=True)
                conn.commit()
                current_app.logger.critical(f'[PRZENIES SERVICE] *** BUFFER COMMIT SUCCESSFUL ***')
                current_app.logger.info(f'✓ Committed {buffer_insert_count} buffer inserts for {next_date.strftime("%Y-%m-%d")}')
                print(f'[PRZENIES SERVICE] BUFFER COMMIT: inserted {buffer_insert_count} records', file=sys.stderr, flush=True)
            except Exception as e:
                current_app.logger.critical(f'[PRZENIES SERVICE] *** ERROR IN BUFFER COMMIT: {str(e)} ***')
                current_app.logger.warning(f'Error committing buffer inserts: {str(e)}')
                conn.rollback()
                print(f'[PRZENIES SERVICE] ROLLBACK EXECUTED: {str(e)}', file=sys.stderr, flush=True)
            
            buffer_insert_cursor.close()
            
            # Delete buffer entries (not needed after creating new plans on next day)
            buffer_deleted = 0
            try:
                import sys
                # Create separate cursor for DELETE (dictionary=True has issues with UPDATE/DELETE)
                delete_cursor = conn.cursor()
                
                # BEFORE: List all records that will be deleted
                delete_cursor.execute("SELECT id, zasyp_id, produkt FROM bufor WHERE DATE(data_planu) = %s", (current_data,))
                before_delete = delete_cursor.fetchall()
                print(f'[PRZENIES SERVICE] BEFORE DELETE: {len(before_delete)} rekordy: {before_delete}', file=sys.stderr, flush=True)
                current_app.logger.critical(f'[PRZENIES SERVICE] BEFORE DELETE: {len(before_delete)} rekordy: {before_delete}')
                
                print(f'[PRZENIES SERVICE] ABOUT TO DELETE FROM bufor WHERE DATE(data_planu) = {current_data}', file=sys.stderr, flush=True)
                current_app.logger.critical(f'[PRZENIES SERVICE] ABOUT TO DELETE FROM bufor WHERE DATE(data_planu) = {current_data}')
                current_app.logger.info(f'[PRZENIES SERVICE] Executing DELETE FROM bufor WHERE DATE(data_planu) = {current_data}')
                
                delete_cursor.execute("""
                    DELETE FROM bufor
                    WHERE DATE(data_planu) = %s
                """, (current_data,))
                
                buffer_deleted = delete_cursor.rowcount
                print(f'[PRZENIES SERVICE] DELETE rowcount={buffer_deleted}', file=sys.stderr, flush=True)
                current_app.logger.critical(f'[PRZENIES SERVICE] DELETE rowcount={buffer_deleted}')
                current_app.logger.info(f'[PRZENIES SERVICE] DELETE executed: rowcount={buffer_deleted}')
                
                delete_cursor.close()
                
                # Commit BEFORE verification to ensure changes are visible
                conn.commit()
                print(f'[PRZENIES SERVICE] COMMIT DONE', file=sys.stderr, flush=True)
                current_app.logger.critical(f'[PRZENIES SERVICE] COMMIT DONE')
                current_app.logger.info(f'[PRZENIES SERVICE] COMMIT executed')
                
                # Verify delete worked - SELECT AFTER
                verify_cursor = conn.cursor()
                verify_cursor.execute('SELECT id, zasyp_id, produkt FROM bufor WHERE DATE(data_planu) = %s', (current_data,))
                after_delete = verify_cursor.fetchall()
                count_after = len(after_delete)
                print(f'[PRZENIES SERVICE] AFTER DELETE: {count_after} rekordy: {after_delete}', file=sys.stderr, flush=True)
                current_app.logger.critical(f'[PRZENIES SERVICE] AFTER DELETE: {count_after} rekordy: {after_delete}')
                print(f'[PRZENIES SERVICE] VERIFY: count_after={count_after}', file=sys.stderr, flush=True)
                current_app.logger.critical(f'[PRZENIES SERVICE] VERIFY: count_after={count_after}')
                current_app.logger.info(f'[PRZENIES SERVICE] Verification: COUNT after DELETE = {count_after}')
                verify_cursor.close()
                current_app.logger.info(f'✓ Usunięto {buffer_deleted} zapisów z buforu na dzień {current_data}')
            except Exception as e:
                current_app.logger.warning(f'Error moving buffer: {str(e)}')
                try:
                    conn.rollback()
                except:
                    pass
            
            conn.close()
            
            # created_count is total number of plans (both Zasyp and Workowanie)
            product_count = created_count // 2
            message = f'✓ Utworzono {product_count} nowych par planów (Zasyp + Workowanie) na dzień {next_date.strftime("%d.%m.%Y")} ({created_count} planów łącznie)'
            
            print(f'[PRZENIES SERVICE] *** RETURNING SUCCESS *** message={message}, created_count={created_count}', file=sys.stderr, flush=True)
            current_app.logger.critical(f'[PRZENIES SERVICE] *** RETURNING SUCCESS *** created_count={created_count}')
            
            return (True, message, created_count)
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error in przenies_niezrealizowane: {str(e)}')
            return (False, f'Błąd serwera: {str(e)}', 0)