"""Leave request service - handles all leave/time-off request operations."""

from datetime import date, datetime, timedelta
from app.db import get_db_connection
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class LeaveRequestService:
    """Service for managing leave requests (wnioski o wolne) and approval workflow."""

    @staticmethod
    def submit_leave_request(pracownik_id: int, typ: str, data_od: date, data_do: date,
                           czas_od: str = None, czas_do: str = None, powod: str = '') -> tuple:
        """
        Submit a new leave request.
        
        Args:
            pracownik_id: Employee ID
            typ: Type of leave (Urlop, Wyjście prywatne, etc.)
            data_od: Start date
            data_do: End date  
            czas_od: Optional start time
            czas_do: Optional end time
            powod: Reason for leave
            
        Returns:
            (success: bool, message: str, request_id: int or None)
        """
        try:
            if not pracownik_id:
                return False, "Brak przypisanego pracownika do konta.", None

            # Validate dates based on leave type
            if typ and typ.lower().startswith('wyj'):
                # Wyjście prywatne - single day allowed
                if not data_od:
                    return False, "Podaj datę wniosku.", None
                if not data_do:
                    data_do = data_od
            else:
                # Regular leave - require date range
                if not data_od or not data_do:
                    # Keep message friendly and include 'data' keyword for tests
                    return False, "Podaj zakres dat (data_od i data_do) wniosku.", None

            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """INSERT INTO wnioski_wolne 
                       (pracownik_id, typ, data_od, data_do, czas_od, czas_do, powod) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (pracownik_id, typ, data_od, data_do, czas_od, czas_do, powod)
                )
                conn.commit()
                request_id = cursor.lastrowid
                return True, "Wniosek złożony pomyślnie.", request_id
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error submitting leave request: %s", str(e))
            return False, "Błąd przy składaniu wniosku.", None

    @staticmethod
    def approve_leave_request(request_id: int, lider_id: int) -> tuple:
        """
        Approve a leave request and increment leave counters.
        
        Args:
            request_id: Leave request ID
            lider_id: Leader/approver ID
            
        Returns:
            (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                # Update request status
                cursor.execute(
                    """UPDATE wnioski_wolne 
                       SET status='approved', decyzja_dnia=NOW(), lider_id=%s 
                       WHERE id=%s""",
                    (lider_id, request_id)
                )
                conn.commit()

                # Get request details for day counting
                cursor.execute(
                    """SELECT pracownik_id, data_od, data_do, typ 
                       FROM wnioski_wolne WHERE id=%s""",
                    (request_id,)
                )
                row = cursor.fetchone()
                if row:
                    pracownik_id, data_od, data_do, typ = row
                    LeaveRequestService._update_leave_counters(
                        cursor, conn, pracownik_id, data_od, data_do, typ
                    )

                return True, "Wniosek zatwierdzony."
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error approving leave request: %s", str(e))
            return False, "Błąd przy zatwierdzaniu wniosku."

    @staticmethod
    def reject_leave_request(request_id: int, lider_id: int) -> tuple:
        """
        Reject a leave request.
        
        Args:
            request_id: Leave request ID
            lider_id: Leader/approver ID
            
        Returns:
            (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """UPDATE wnioski_wolne 
                       SET status='rejected', decyzja_dnia=NOW(), lider_id=%s 
                       WHERE id=%s""",
                    (lider_id, request_id)
                )
                conn.commit()
                return True, "Wniosek odrzucony."
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error rejecting leave request: %s", str(e))
            return False, "Błąd przy odrzucaniu wniosku."

    @staticmethod
    def get_requests_for_day(pracownik_id: int, date_str: str) -> dict:
        """
        Get all leave requests for an employee on a specific date.
        
        Args:
            pracownik_id: Employee ID
            date_str: Date string (YYYY-MM-DD)
            
        Returns:
            {'wnioski': list of requests, 'error': error message or None}
        """
        try:
            if not pracownik_id or not date_str:
                return {'error': 'missing parameters', 'wnioski': []}

            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """SELECT id, typ, data_od, data_do, czas_od, czas_do, powod, status, zlozono 
                       FROM wnioski_wolne 
                       WHERE pracownik_id=%s AND data_od <= %s AND data_do >= %s 
                       ORDER BY zlozono DESC""",
                    (pracownik_id, date_str, date_str)
                )
                rows = cursor.fetchall()

                wnioski = []
                for r in rows:
                    wnioski.append({
                        'id': r[0],
                        'typ': r[1],
                        'data_od': str(r[2]),
                        'data_do': str(r[3]),
                        'czas_od': str(r[4]) if r[4] else None,
                        'czas_do': str(r[5]) if r[5] else None,
                        'powod': r[6],
                        'status': r[7],
                        'zlozono': str(r[8])
                    })
                return {'wnioski': wnioski, 'error': None}

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error fetching wnioski for day: %s", str(e))
            return {'error': 'server error', 'wnioski': []}

    @staticmethod
    def get_summary_for_employee(pracownik_id: int) -> dict:
        """
        Get employee leave summary (current month: attendances, hours by type, leave counters).
        
        Args:
            pracownik_id: Employee ID
            
        Returns:
            {'obecnosci': int, 'typy': dict, 'wyjscia_hours': float, 
             'urlop_biezacy': int, 'urlop_zalegly': int, 'error': str or None}
        """
        try:
            if not pracownik_id:
                return {'error': 'missing pracownik_id'}

            try:
                pid = int(pracownik_id)
            except (ValueError, TypeError):
                return {'error': 'invalid pracownik_id'}

            # Current month date range
            teraz = datetime.now()
            d_od = date(teraz.year, teraz.month, 1)
            d_do = date(teraz.year, teraz.month, teraz.day)

            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                # Count attendances
                cursor.execute(
                    """SELECT COUNT(1) FROM obsada_zmiany 
                       WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s""",
                    (pid, d_od, d_do)
                )
                rr = cursor.fetchone()
                obecnosci = int(rr[0] or 0) if rr else 0

                # Hours by type
                cursor.execute(
                    """SELECT COALESCE(typ, ''), COALESCE(SUM(ilosc_godzin),0) 
                       FROM obecnosc 
                       WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s 
                       GROUP BY typ""",
                    (pid, d_od, d_do)
                )
                typy = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}

                # Private exit hours
                try:
                    cursor.execute(
                        """SELECT COALESCE(SUM(TIME_TO_SEC(wyjscie_do)-TIME_TO_SEC(wyjscie_od))/3600,0) 
                           FROM obecnosc 
                           WHERE pracownik_id=%s AND typ='Wyjscie prywatne' 
                           AND data_wpisu BETWEEN %s AND %s""",
                        (pid, d_od, d_do)
                    )
                    rr2 = cursor.fetchone()
                    wyjscia_hours = float(rr2[0] or 0) if rr2 else 0.0
                except Exception:
                    wyjscia_hours = 0.0

                # Leave counters from pracownicy table
                try:
                    cursor.execute(
                        """SELECT COALESCE(urlop_biezacy,0), COALESCE(urlop_zalegly,0) 
                           FROM pracownicy WHERE id=%s""",
                        (pid,)
                    )
                    rr = cursor.fetchone()
                    if rr:
                        # be tolerant to different shapes
                        urlop_biezacy = int(rr[0] or 0) if len(rr) > 0 else 0
                        urlop_zalegly = int(rr[1] or 0) if len(rr) > 1 else 0
                    else:
                        urlop_biezacy = 0
                        urlop_zalegly = 0
                except Exception:
                    urlop_biezacy = 0
                    urlop_zalegly = 0

                return {
                    'obecnosci': obecnosci,
                    'typy': typy,
                    'wyjscia_hours': wyjscia_hours,
                    'urlop_biezacy': urlop_biezacy,
                    'urlop_zalegly': urlop_zalegly,
                    'error': None
                }

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error building leave summary: %s", str(e))
            return {'error': 'server error'}

    # Private helper methods

    @staticmethod
    def _update_leave_counters(cursor, conn, pracownik_id: int, data_od: date, 
                               data_do: date, typ: str):
        """
        Update leave counters (urlop_biezacy, urlop_zalegly) based on approved leave request.
        
        Args:
            cursor: Database cursor
            conn: Database connection
            pracownik_id: Employee ID
            data_od: Start date
            data_do: End date
            typ: Leave type
        """
        try:
            # Calculate inclusive number of days
            try:
                days = (data_do - data_od).days + 1 if (data_od and data_do) else 0
            except (TypeError, AttributeError):
                days = 0

            if days > 0:
                # Ensure columns exist
                try:
                    cursor.execute("ALTER TABLE pracownicy ADD COLUMN IF NOT EXISTS urlop_biezacy INT DEFAULT 0")
                    cursor.execute("ALTER TABLE pracownicy ADD COLUMN IF NOT EXISTS urlop_zalegly INT DEFAULT 0")
                except Exception:
                    # Some MySQL versions may not support IF NOT EXISTS
                    try:
                        cursor.execute("ALTER TABLE pracownicy ADD COLUMN urlop_biezacy INT DEFAULT 0")
                        cursor.execute("ALTER TABLE pracownicy ADD COLUMN urlop_zalegly INT DEFAULT 0")
                    except Exception:
                        pass

                # Decide which counter to increment
                if typ and 'zaleg' in typ.lower():
                    cursor.execute(
                        """UPDATE pracownicy 
                           SET urlop_zalegly = COALESCE(urlop_zalegly,0) + %s 
                           WHERE id=%s""",
                        (days, pracownik_id)
                    )
                else:
                    cursor.execute(
                        """UPDATE pracownicy 
                           SET urlop_biezacy = COALESCE(urlop_biezacy,0) + %s 
                           WHERE id=%s""",
                        (days, pracownik_id)
                    )
                conn.commit()

        except Exception as e:
            current_app.logger.exception("Error updating leave counters: %s", str(e))
            try:
                conn.rollback()
            except Exception:
                pass
