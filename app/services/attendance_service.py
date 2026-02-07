"""Attendance and schedule management service."""

from datetime import date, datetime, timedelta
from app.db import get_db_connection
from flask import current_app, render_template
import logging

logger = logging.getLogger(__name__)


class AttendanceService:
    """Service for managing employee attendance, schedules, and schedule panels."""

    @staticmethod
    def add_to_schedule(sekcja: str, pracownik_id: int, date_str: str = None) -> tuple:
        """
        Add employee to schedule (obsada) for a section and date.
        Automatically creates an attendance record if none exists.
        
        Args:
            sekcja: Section name (Zasyp, Workowanie, Magazyn)
            pracownik_id: Employee ID
            date_str: Date string (YYYY-MM-DD), defaults to today
            
        Returns:
            (success: bool, inserted_id: int or None, employee_name: str)
        """
        try:
            if not sekcja or not pracownik_id:
                return False, None, ""

            # Parse date
            try:
                add_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
            except (ValueError, TypeError):
                add_date = date.today()

            conn = get_db_connection()
            cursor = conn.cursor()
            inserted_id = None

            try:
                # Insert schedule record
                cursor.execute(
                    """INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) 
                       VALUES (%s, %s, %s)""",
                    (add_date, sekcja, pracownik_id)
                )

                # Retrieve inserted ID
                try:
                    cursor.execute(
                        """SELECT id FROM obsada_zmiany 
                           WHERE data_wpisu=%s AND sekcja=%s AND pracownik_id=%s 
                           ORDER BY id DESC LIMIT 1""",
                        (add_date, sekcja, pracownik_id)
                    )
                    inserted_row = cursor.fetchone()
                    inserted_id = inserted_row[0] if inserted_row else None
                except Exception:
                    inserted_id = None

                # Auto-create attendance record if needed
                try:
                    default_hours = 8
                    cursor.execute(
                        """SELECT COUNT(1) FROM obecnosc 
                           WHERE pracownik_id=%s AND data_wpisu=%s""",
                        (pracownik_id, add_date)
                    )
                    exists = int(cursor.fetchone()[0] or 0)
                    if not exists:
                        cursor.execute(
                            """INSERT INTO obecnosc 
                               (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) 
                            VALUES (%s, %s, %s, %s, %s)""",
                            (add_date, pracownik_id, 'Obecność', default_hours, 'Automatyczne z obsady')
                        )
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                conn.commit()

                # Fetch employee name
                try:
                    cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id=%s", (pracownik_id,))
                    row = cursor.fetchone()
                    name = row[0] if row else ""
                except Exception:
                    name = ""

                return True, inserted_id, name

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error adding employee to schedule: %s", str(e))
            return False, None, ""

    @staticmethod
    def remove_from_schedule(obsada_id: int) -> bool:
        """
        Remove employee from schedule.
        Deletes all schedule records for that employee/date/section combination.
        
        Args:
            obsada_id: Schedule record ID
            
        Returns:
            success: bool
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                # Get details of the record to delete
                cursor.execute(
                    """SELECT pracownik_id, data_wpisu, sekcja 
                       FROM obsada_zmiany WHERE id=%s""",
                    (obsada_id,)
                )
                row = cursor.fetchone()
                if row:
                    pracownik_id, data_wpisu, sekcja = row
                    # Delete all matching records (handles duplicates)
                    cursor.execute(
                        """DELETE FROM obsada_zmiany 
                           WHERE pracownik_id=%s AND data_wpisu=%s AND sekcja=%s""",
                        (pracownik_id, data_wpisu, sekcja)
                    )
                    conn.commit()
                    return True
                return False

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error removing employee from schedule: %s", str(e))
            return False

    @staticmethod
    def delete_absence_record(absence_id: int) -> bool:
        """
        Delete an absence/presence record.
        
        Args:
            absence_id: Absence record ID
            
        Returns:
            success: bool
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("DELETE FROM obecnosc WHERE id=%s", (absence_id,))
                conn.commit()
                return True

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error deleting absence record: %s", str(e))
            return False

    @staticmethod
    def save_shift_leaders(date_str: str, lider_psd_id: int = None, 
                          lider_agro_id: int = None) -> bool:
        """
        Save shift leaders for a specific date (upsert operation).
        
        Args:
            date_str: Date string (YYYY-MM-DD)
            lider_psd_id: PSD leader ID  
            lider_agro_id: AGRO leader ID
            
        Returns:
            success: bool
        """
        try:
            # Parse date
            try:
                qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
            except (ValueError, TypeError):
                qdate = date.today()

            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                # Upsert leaders for that date
                cursor.execute(
                    """INSERT INTO obsada_liderzy (data_wpisu, lider_psd_id, lider_agro_id) 
                       VALUES (%s, %s, %s) 
                       ON DUPLICATE KEY UPDATE 
                       lider_psd_id=VALUES(lider_psd_id), 
                       lider_agro_id=VALUES(lider_agro_id)""",
                    (qdate, lider_psd_id, lider_agro_id)
                )
                conn.commit()
                return True

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Error saving shift leaders: %s", str(e))
            return False

    # Panel data methods (return rendered HTML)

    @staticmethod
    def get_pending_requests_panel() -> str:
        """
        Get HTML fragment with list of pending leave requests.
        
        Returns:
            HTML string
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, 
                              w.czas_od, w.czas_do, w.powod, w.zlozono 
                       FROM wnioski_wolne w 
                       JOIN pracownicy p ON w.pracownik_id = p.id 
                       WHERE w.status = 'pending' 
                       ORDER BY w.zlozono DESC 
                       LIMIT 200"""
                )
                raw = cursor.fetchall()

                wnioski = []
                for r in raw:
                    wnioski.append({
                        'id': r[0],
                        'pracownik': r[1],
                        'typ': r[2],
                        'data_od': r[3],
                        'data_do': r[4],
                        'czas_od': r[5],
                        'czas_do': r[6],
                        'powod': r[7],
                        'zlozono': r[8]
                    })

                return render_template('panels/wnioski_panel.html', wnioski=wnioski)

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Failed to build wnioski panel: %s", str(e))
            return render_template('panels/wnioski_panel.html', wnioski=[])

    @staticmethod
    def get_planned_leaves_panel() -> str:
        """
        Get HTML fragment with planned leaves (next 60 days).
        
        Returns:
            HTML string
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                end_date = date.today() + timedelta(days=60)
                cursor.execute(
                    """SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, 
                              w.czas_od, w.czas_do, w.status 
                       FROM wnioski_wolne w 
                       JOIN pracownicy p ON w.pracownik_id = p.id 
                       WHERE w.data_od <= %s AND w.data_do >= %s 
                       ORDER BY w.data_od ASC 
                       LIMIT 500""",
                    (end_date, date.today())
                )
                raw = cursor.fetchall()

                planned = []
                for r in raw:
                    planned.append({
                        'id': r[0],
                        'pracownik': r[1],
                        'typ': r[2],
                        'data_od': r[3],
                        'data_do': r[4],
                        'czas_od': r[5],
                        'czas_do': r[6],
                        'status': r[7]
                    })

                return render_template('panels/planowane_panel.html', planned_leaves=planned)

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Failed to build planned leaves panel: %s", str(e))
            return render_template('panels/planowane_panel.html', planned_leaves=[])

    @staticmethod
    def get_recent_absences_panel() -> str:
        """
        Get HTML fragment with recent absences (last 30 days).
        
        Returns:
            HTML string
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                since = date.today() - timedelta(days=30)
                cursor.execute(
                    """SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, 
                              o.ilosc_godzin, o.komentarz 
                       FROM obecnosc o 
                       JOIN pracownicy p ON o.pracownik_id = p.id 
                       WHERE o.data_wpisu BETWEEN %s AND %s 
                       ORDER BY o.data_wpisu DESC 
                       LIMIT 500""",
                    (since, date.today())
                )
                raw = cursor.fetchall()

                recent = []
                for r in raw:
                    recent.append({
                        'id': r[0],
                        'pracownik': r[1],
                        'typ': r[2],
                        'data': r[3],
                        'godziny': r[4],
                        'komentarz': r[5]
                    })

                return render_template('panels/obecnosci_panel.html', recent_absences=recent)

            finally:
                conn.close()

        except Exception as e:
            current_app.logger.exception("Failed to build absences panel: %s", str(e))
            return render_template('panels/obecnosci_panel.html', recent_absences=[])
