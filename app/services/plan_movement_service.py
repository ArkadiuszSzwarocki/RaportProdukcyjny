"""Production plan movement service for moving and shifting orders."""

from datetime import date
from app.db import get_db_connection
from flask import current_app


class PlanMovementService:
    """Service for managing plan movement operations (move to different section, shift order)."""

    @staticmethod
    def move_plan_to_section(plan_id, target_sekcja):
        """Move a plan to a different section.
        
        Args:
            plan_id: ID of plan to move
            target_sekcja: Target section name
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current plan info
            cursor.execute(
                "SELECT sekcja, produkt, data_planu FROM plan_produkcji WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            
            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')
            
            current_sekcja = res[0]
            produkt = res[1]
            data_planu = res[2]
            
            # Cannot move if already in target section
            if current_sekcja == target_sekcja:
                conn.close()
                return (False, f'Zlecenie już jest w sekcji {target_sekcja}.')
            
            # Get next sequence in target section
            cursor.execute(
                "SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s AND sekcja=%s",
                (data_planu, target_sekcja)
            )
            res_seq = cursor.fetchone()
            next_seq = (res_seq[0] if res_seq and res_seq[0] else 0) + 1
            
            # Update plan: change section and reset sequence
            cursor.execute(
                "UPDATE plan_produkcji SET sekcja=%s, kolejnosc=%s WHERE id=%s",
                (target_sekcja, next_seq, plan_id)
            )
            
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan moved: id={plan_id}, {current_sekcja} -> {target_sekcja}')
            return (True, f'Zlecenie {produkt} przeniesione do {target_sekcja}.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error moving plan {plan_id}')
            return (False, f'Błąd przy przeniesieniu: {str(e)}')

    @staticmethod
    def shift_plan_order(plan_id, kierunek):
        """Shift a plan up or down in the queue (change order).
        
        Args:
            plan_id: ID of plan to shift
            kierunek: Direction ('up'/'w_gore' or 'down'/'w_dol')
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            if kierunek not in ['up', 'w_gore', 'down', 'w_dol']:
                return (False, f'Niepoprawny kierunek: {kierunek}')
            
            is_up = kierunek in ['up', 'w_gore']
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current plan info
            cursor.execute(
                "SELECT sekcja, kolejnosc, data_planu, produkt FROM plan_produkcji WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            
            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')
            
            sekcja = res[0]
            current_seq = res[1]
            data_planu = res[2]
            produkt = res[3]
            
            # Find adjacent plan in target direction
            if is_up:
                # Find plan with lower sequence (move up)
                cursor.execute("""
                    SELECT id, kolejnosc FROM plan_produkcji 
                    WHERE sekcja=%s AND data_planu=%s AND kolejnosc < %s
                    ORDER BY kolejnosc DESC
                    LIMIT 1
                """, (sekcja, data_planu, current_seq))
            else:
                # Find plan with higher sequence (move down)
                cursor.execute("""
                    SELECT id, kolejnosc FROM plan_produkcji
                    WHERE sekcja=%s AND data_planu=%s AND kolejnosc > %s
                    ORDER BY kolejnosc ASC
                    LIMIT 1
                """, (sekcja, data_planu, current_seq))
            
            adjacent = cursor.fetchone()
            
            if not adjacent:
                conn.close()
                return (False, 'Nie można przesunąć - brak sąsiedniego zlecenia.')
            
            adjacent_id = adjacent[0]
            adjacent_seq = adjacent[1]
            
            # Swap sequences
            cursor.execute(
                "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s",
                (adjacent_seq, plan_id)
            )
            cursor.execute(
                "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s",
                (current_seq, adjacent_id)
            )
            
            conn.commit()
            conn.close()
            
            direction_label = 'w górę' if is_up else 'w dół'
            current_app.logger.info(f'Plan shifted: id={plan_id}, {direction_label}')
            return (True, f'Zlecenie {produkt} przesunięte {direction_label}.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error shifting plan {plan_id}')
            return (False, f'Błąd przy przesunięciu: {str(e)}')

    @staticmethod
    def reorder_plans(section, date_planu, new_order):
        """Reorder plans within a section for a specific date.
        
        Args:
            section: Section name
            date_planu: Date (YYYY-MM-DD or date object)
            new_order: List of plan IDs in desired order
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            if isinstance(date_planu, date):
                date_planu = date_planu.isoformat()
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Update each plan's sequence based on position in new_order
            for seq, plan_id in enumerate(new_order, start=1):
                cursor.execute(
                    "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s AND sekcja=%s AND data_planu=%s",
                    (seq, plan_id, section, date_planu)
                )
            
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plans reordered: section={section}, date={date_planu}')
            return (True, f'Kolejność zleceń w sekcji {section} zmieniona.')
            
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error reordering plans')
            return (False, f'Błąd przy zmianie kolejności: {str(e)}')

    @staticmethod
    def get_plan_queue_for_section(section, date_planu):
        """Get ordered list of plans in a section for a date.
        
        Args:
            section: Section name
            date_planu: Date (YYYY-MM-DD or date object)
            
        Returns:
            List of plans ordered by kolejnosc, or empty list on error
        """
        try:
            if isinstance(date_planu, date):
                date_planu = date_planu.isoformat()
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, produkt, tonaz, status, kolejnosc, tonaz_rzeczywisty
                FROM plan_produkcji
                WHERE sekcja=%s AND data_planu=%s AND (is_deleted=0 OR is_deleted IS NULL)
                ORDER BY kolejnosc ASC
            """, (section, date_planu))
            
            rows = cursor.fetchall()
            conn.close()
            
            plans = []
            for row in rows:
                plans.append({
                    'id': row[0],
                    'produkt': row[1],
                    'tonaz': row[2],
                    'status': row[3],
                    'kolejnosc': row[4],
                    'tonaz_rzeczywisty': row[5]
                })
            
            return plans
            
        except Exception as e:
            current_app.logger.exception(f'Error getting plan queue')
            return []
