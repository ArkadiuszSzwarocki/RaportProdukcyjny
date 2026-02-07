"""Production planning service for managing production plans."""

from datetime import date, datetime
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
        """Soft delete a plan (mark as deleted).
        
        Args:
            plan_id: ID of plan to delete
            
        Returns:
            Tuple (success: bool, message: str)
        """
        print(f'\n🔥 [SERVICE-1] delete_plan({plan_id}) START')
        try:
            print(f'🔥 [SERVICE-2] Łączę się z bazą...')
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if plan exists and its status
            print(f'🔥 [SERVICE-3] Szukam planu ID={plan_id}...')
            cursor.execute("SELECT status, produkt FROM plan_produkcji WHERE id=%s", (plan_id,))
            res = cursor.fetchone()
            print(f'🔥 [SERVICE-4] Wynik SELECT: {res}')
            
            if not res:
                print(f'🔥 [SERVICE-5] Plan nie znaleziony!')
                conn.close()
                return (False, 'Zlecenie nie istnieje.')
            
            status = res[0]
            produkt = res[1]
            print(f'🔥 [SERVICE-6] Plan znaleziony: status={status}, produkt={produkt}')
            
            # Cannot delete if in progress or completed
            if status in ['w toku', 'zakonczone']:
                print(f'🔥 [SERVICE-7] Plan ma status zabroniony do usunięcia: {status}')
                conn.close()
                return (False, 'Nie można usunąć zlecenia w toku lub już zakończonego.')
            
            # Soft delete: set is_deleted=1, deleted_at=NOW()
            print(f'🔥 [SERVICE-8] Wykonuję UPDATE...')
            cursor.execute(
                "UPDATE plan_produkcji SET is_deleted=1, deleted_at=NOW() WHERE id=%s",
                (plan_id,)
            )
            print(f'🔥 [SERVICE-9] UPDATE zakończony, rowcount={cursor.rowcount}')
            conn.commit()
            print(f'🔥 [SERVICE-10] COMMIT wykonany')
            conn.close()
            print(f'🔥 [SERVICE-11] Połączenie zamknięte')
            
            current_app.logger.info(f'Plan deleted: id={plan_id}, produkt={produkt}')
            msg = f'Zlecenie {produkt} zostało usunięte z planu.'
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
            
            if not res[0]:  # is_deleted = 0
                conn.close()
                return (False, 'To zlecenie nie jest usunięte.')
            
            # Restore: set is_deleted=0, deleted_at=NULL
            cursor.execute(
                "UPDATE plan_produkcji SET is_deleted=0, deleted_at=NULL WHERE id=%s",
                (plan_id,)
            )
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan restored: id={plan_id}, produkt={res[1]}')
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
            
            sekcja = res[0]
            produkt = res[1]
            
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
            return (True, f'Zlecenie {produkt} wznowione.')
            
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
            
            if status in ['w toku', 'zakonczone']:
                print(f'📅 [SERVICE-7] Plan has blocking status!')
                return False, 'Nie można przesunąć planu w toku lub zakończonego.'
            
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
            return True, 'Plan przesunięty na nową datę.'
            
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
