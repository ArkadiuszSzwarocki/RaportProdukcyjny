"""Production planning service - status logic."""

from datetime import date, datetime, timedelta
import traceback
import logging
from flask import current_app, request, session
from app.db import get_db_connection, get_table_name, refresh_bufor_queue

class PlanningStatusService:
    """Service for status operations."""

    @staticmethod
    def restore_plan(plan_id, linia='PSD'):
        """Restore (un-delete) a deleted plan.
        
        Args:
            plan_id: ID of plan to restore
            
        Returns:
            Tuple (success: bool, message: str)
        """
        table_plan = get_table_name('plan_produkcji', linia)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if plan exists and is deleted
            cursor.execute(
                f"SELECT is_deleted, produkt, status FROM {table_plan} WHERE id=%s",
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
                f"UPDATE {table_plan} SET is_deleted=0, deleted_at=NULL WHERE id=%s",
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
    def resume_plan(plan_id, linia='PSD'):
        """Resume a paused/zaplanowane plan (change status to 'w toku').
        
        Args:
            plan_id: ID of plan to resume
            
        Returns:
            Tuple (success: bool, message: str)
        """
        table_plan = get_table_name('plan_produkcji', linia)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get section of this plan
            cursor.execute(
                f"SELECT sekcja, produkt, status FROM {table_plan} WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()

            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            sekcja = res[0] if len(res) > 0 else None
            produkt = res[1] if len(res) > 1 else None
            
            # Set all other plans in this section to zaplanowane (pause them)
            if str(linia).upper() == 'AGRO':
                cursor.execute(
                    f"UPDATE {table_plan} SET status='zawieszone', "
                    "czas_pracy_sekundy = czas_pracy_sekundy + TIMESTAMPDIFF(SECOND, COALESCE(ostatnie_wznowienie, NOW()), NOW()) "
                    "WHERE sekcja=%s AND status='w toku'",
                    (sekcja,)
                )
            else:
                cursor.execute(
                    f"UPDATE {table_plan} SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'",
                    (sekcja,)
                )
            
            # Log pause of other plans (diagnostic)
            try:
                status_logger = logging.getLogger('status_changes')
                status_logger.info(f"action=pause_section sekcja={sekcja} effected_by=resume_plan caller=PlanningStatusService.resume_plan user={session.get('login') if session else 'unknown'}")
            except Exception:
                pass

            # Set this plan to w toku (resume)
            if str(linia).upper() == 'AGRO':
                cursor.execute(
                    f"UPDATE {table_plan} SET status='w toku', real_stop=NULL, ostatnie_wznowienie=NOW() WHERE id=%s",
                    (plan_id,)
                )
            else:
                cursor.execute(
                    f"UPDATE {table_plan} SET status='w toku', real_stop=NULL WHERE id=%s",
                    (plan_id,)
                )
            
            # Log resume event
            try:
                status_logger = logging.getLogger('status_changes')
                old_status = res[2] if len(res) > 2 else 'unknown'
                status_logger.info(f"action=resume plan_id={plan_id} old={old_status} new=w_toku user={session.get('login') if session else 'unknown'} endpoint={request.path if request else 'cli'} caller=PlanningStatusService.resume_plan")
            except Exception:
                pass
            
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
    def suspend_plan(plan_id, linia='AGRO'):
        """Suspend an active plan (change status to 'zawieszone') and calculate elapsed time.
        
        Args:
            plan_id: ID of plan to suspend
            
        Returns:
            Tuple (success: bool, message: str)
        """
        table_plan = get_table_name('plan_produkcji', linia)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                f"SELECT produkt FROM {table_plan} WHERE id=%s AND status='w toku'",
                (plan_id,)
            )
            res = cursor.fetchone()
            if not res:
                conn.close()
                return (False, 'Zlecenie nie jest w toku lub nie istnieje.')
                
            produkt = res[0]
            
            if str(linia).upper() == 'AGRO':
                cursor.execute(
                    f"UPDATE {table_plan} SET status='zawieszone', "
                    "czas_pracy_sekundy = czas_pracy_sekundy + TIMESTAMPDIFF(SECOND, COALESCE(ostatnie_wznowienie, NOW()), NOW()) "
                    "WHERE id=%s",
                    (plan_id,)
                )
            else:
                cursor.execute(
                    f"UPDATE {table_plan} SET status='zaplanowane' WHERE id=%s",
                    (plan_id,)
                )
                
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan suspended: id={plan_id}, produkt={produkt}')
            return (True, 'Zlecenie zostało zawieszone.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error suspending plan {plan_id}')
            return (False, f'Błąd przy zawieszaniu: {str(e)}')

    @staticmethod
    def change_status(plan_id, new_status, linia='PSD'):
        """Change plan status.
        
        Args:
            plan_id: ID of plan
            new_status: New status value
            
        Returns:
            Tuple (success: bool, message: str)
        """
        table_plan = get_table_name('plan_produkcji', linia)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current plan info
            cursor.execute(
                f"SELECT status, produkt FROM {table_plan} WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            
            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')
            
            old_status = res[0]
            produkt = res[1]
            
            # Update status
            if str(linia).upper() == 'AGRO' and old_status == 'w toku' and new_status in ('zakonczone', 'zawieszone'):
                cursor.execute(
                    f"UPDATE {table_plan} SET status=%s, "
                    "czas_pracy_sekundy = czas_pracy_sekundy + TIMESTAMPDIFF(SECOND, COALESCE(ostatnie_wznowienie, NOW()), NOW()) "
                    "WHERE id=%s",
                    (new_status, plan_id)
                )
            else:
                cursor.execute(
                    f"UPDATE {table_plan} SET status=%s WHERE id=%s",
                    (new_status, plan_id)
                )
            conn.commit()
            conn.close()
            
            if new_status == 'zakonczone':
                try:
                    import traceback
                    caller = traceback.extract_stack()[-3]
                    caller_str = f"{caller}"
                    current_app.logger.critical(f"[TRAP-ZAKONCZONE] Zlecenie ID={plan_id} ('{produkt}') status manualnie zmieniony na 'zakonczone' przez funkcję change_status. Caller: {caller}, user: {session.get('login') if 'session' in globals() else 'unknown'}")
                except Exception:
                    caller_str = "unknown"
                    current_app.logger.critical(f"[TRAP-ZAKONCZONE] Zlecenie ID={plan_id} ('{produkt}') status manualnie zmieniony na 'zakonczone' przez funkcję change_status. Caller: unknown")
                
                try:
                    from app.core.audit import audit_log
                    audit_log('[TRAP] Zmiana Statusu Zlecenia', f'Zakończono ID={plan_id} ({produkt}). Skrypt: {caller_str}')
                except Exception:
                    pass

            current_app.logger.info(f'Plan status changed: id={plan_id}, {old_status} -> {new_status}')
            try:
                status_logger = logging.getLogger('status_changes')
                status_logger.info(f"action=change_status plan_id={plan_id} old={old_status} new={new_status} user={session.get('login') if session else 'unknown'} endpoint={request.path if request else 'cli'} caller=PlanningStatusService.change_status")
            except Exception:
                pass
            return (True, f'Status dla {produkt} zmieniony na {new_status}.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error changing status for plan {plan_id}')
            return (False, f'Błąd przy zmianie statusu: {str(e)}')

    @staticmethod
    def ensure_status_after_tonaz_update(plan_id, linia='PSD'):
        """
        After tonaz_rzeczywisty is updated, ensure status reflects actual execution.
        If tonaz_rzeczywisty > 0 and status='zaplanowane', change to 'w toku'.
        
        Args:
            plan_id: Plan ID to validate
            linia: Hall identifier (PSD or AGRO)
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            from app.db import get_table_name
            table_plan = get_table_name('plan_produkcji', linia)
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Check current state
            cursor.execute(f"""
                SELECT id, status, tonaz_rzeczywisty, real_start, real_stop
                FROM {table_plan}
                WHERE id=%s
            """, (plan_id,))
            
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return (False, 'Plan nie istnieje.')
            
            status = result['status']
            tonaz_rz = result['tonaz_rzeczywisty'] or 0
            real_start = result['real_start']
            
            # Logic: If tonaz_rzeczywisty > 0 but status is still 'zaplanowane'
            # and no real_start, update to 'w toku'
            if tonaz_rz > 0 and status == 'zaplanowane' and not real_start:
                cursor.execute(f"""
                    UPDATE {table_plan}
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
                        current_app.logger.critical(f'[TRAP-ZAKONCZONE] Zlecenie ID={plan_id} zostało ZAKOŃCZONE automatycznie przez funkcję validate_and_fix_anomalies (API). Endpoint: /api/admin/fix-anomalies')
                        try:
                            from app.core.audit import audit_log
                            audit_log('[TRAP] Automatyczne Zamknięcie', f'Naprawa anomalii dla ID={plan_id} ({produkt}) przez API')
                        except Exception:
                            pass
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

