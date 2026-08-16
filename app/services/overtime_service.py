"""Overtime service - handles all overtime request operations."""

from datetime import date, datetime
from app.db import get_db_connection
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class OvertimeService:
    """Service for managing overtime requests (nadgodziny) and approval workflow."""

    @staticmethod
    def submit_overtime_request(pracownik_id: int, data: date, ilosc_nadgodzin: float, powod: str = '') -> tuple:
        """
        Submit a new overtime request.
        
        Args:
            pracownik_id: Employee ID
            data: Date of overtime
            ilosc_nadgodzin: Number of overtime hours
            powod: Reason for overtime
            
        Returns:
            (success: bool, message: str, request_id: int or None)
        """
        try:
            if not pracownik_id:
                return False, "Brak przypisanego pracownika do konta.", None
            
            if not data:
                return False, "Podaj datę nadgodzin.", None
            
            if not ilosc_nadgodzin or ilosc_nadgodzin <= 0:
                return False, "Podaj poprawną liczbę godzin (> 0).", None
            
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """INSERT INTO nadgodziny 
                       (pracownik_id, data, ilosc_nadgodzin, powod) 
                    VALUES (%s, %s, %s, %s)""",
                    (pracownik_id, data, ilosc_nadgodzin, powod)
                )
                conn.commit()
                request_id = cursor.lastrowid
                return True, "Wniosek o nadgodziny złożony pomyślnie.", request_id
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error submitting overtime request: %s", str(e))
            return False, "Błąd przy składaniu wniosku o nadgodziny.", None

    @staticmethod
    def approve_overtime_request(request_id: int, lider_id: int) -> tuple:
        """
        Approve an overtime request.
        
        Args:
            request_id: Overtime request ID
            lider_id: Leader/approver ID
            
        Returns:
            (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """UPDATE nadgodziny 
                       SET status='approved', decyzja_dnia=NOW(), lider_id=%s 
                       WHERE id=%s""",
                    (lider_id, request_id)
                )
                conn.commit()
                return True, "Wniosek o nadgodziny zatwierdzony."
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error approving overtime request: %s", str(e))
            return False, "Błąd przy zatwierdzaniu wniosku o nadgodziny."

    @staticmethod
    def reject_overtime_request(request_id: int, lider_id: int) -> tuple:
        """
        Reject an overtime request.
        
        Args:
            request_id: Overtime request ID
            lider_id: Leader/approver ID
            
        Returns:
            (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """UPDATE nadgodziny 
                       SET status='rejected', decyzja_dnia=NOW(), lider_id=%s 
                       WHERE id=%s""",
                    (lider_id, request_id)
                )
                conn.commit()
                return True, "Wniosek o nadgodziny odrzucony."
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error rejecting overtime request: %s", str(e))
            return False, "Błąd przy odrzucaniu wniosku o nadgodziny."

    @staticmethod
    def get_pending_requests(lider_id: int = None, limit: int = 200) -> list:
        """
        Get pending overtime requests.
        
        Args:
            lider_id: (Optional) Filter for specific leader
            limit: Max number of requests to return
            
        Returns:
            List of dicts with request data
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    """SELECT n.id, p.imie_nazwisko, n.data, n.ilosc_nadgodzin, 
                              n.powod, n.zlozono
                       FROM nadgodziny n
                       JOIN pracownicy p ON n.pracownik_id = p.id
                       WHERE n.status = 'pending'
                       ORDER BY n.zlozono DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cursor.fetchall() or []
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error getting pending overtime requests: %s", str(e))
            return []

    @staticmethod
    def get_user_requests(pracownik_id: int) -> list:
        """
        Get all overtime requests for a specific employee.
        
        Args:
            pracownik_id: Employee ID
            
        Returns:
            List of dicts with request data
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    """SELECT n.id, n.data, n.ilosc_nadgodzin, n.powod, n.status, n.zlozono
                       FROM nadgodziny n
                       WHERE n.pracownik_id = %s
                       ORDER BY n.data DESC""",
                    (pracownik_id,)
                )
                return cursor.fetchall() or []
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error getting user overtime requests: %s", str(e))
            return []

    @staticmethod
    def get_approved_overtime_for_date(pracownik_id: int, data: date) -> float:
        """
        Get total approved overtime hours for an employee on a specific date.
        
        Args:
            pracownik_id: Employee ID
            data: Date
            
        Returns:
            Total overtime hours (0 if none)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """SELECT COALESCE(SUM(ilosc_nadgodzin), 0) 
                       FROM nadgodziny
                       WHERE pracownik_id = %s AND data = %s AND status = 'approved'""",
                    (pracownik_id, data)
                )
                result = cursor.fetchone()
                return result[0] if result else 0.0
            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error getting approved overtime: %s", str(e))
            return 0.0
