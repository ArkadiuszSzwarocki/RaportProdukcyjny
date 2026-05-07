"""Production plan movement service for moving and shifting orders."""

from datetime import date
from app.db import get_db_connection, get_table_name
from flask import current_app


class PlanMovementService:
    """Service for managing plan movement operations (move to different section, shift order)."""

    _LOCKED_STATUSES = {'w toku', 'zakonczone'}

    @staticmethod
    def renormalize_sequences(cursor, table_name, data_planu, sekcja=None):
        """Renormalize kolejnosc for a given date (sequential 1, 2, 3...) filtering deleted rows."""
        query = f"SELECT id FROM {table_name} WHERE data_planu=%s AND (is_deleted=0 OR is_deleted IS NULL)"
        params = [data_planu]
        if sekcja:
            if sekcja.lower() in ['zasyp', 'czyszczenie']:
                query += " AND LOWER(sekcja) IN ('zasyp', 'czyszczenie')"
            else:
                query += " AND sekcja=%s"
                params.append(sekcja)
        query += " ORDER BY kolejnosc ASC, id ASC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        for idx, row in enumerate(rows, start=1):
            cursor.execute(
                f"UPDATE {table_name} SET kolejnosc=%s WHERE id=%s",
                (idx, row[0])
            )

    @staticmethod
    def move_plan_to_section(plan_id, target_sekcja, linia='PSD'):
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
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(
                f"SELECT sekcja, produkt, data_planu FROM {table_plan} WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()

            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            # Be tolerant to different shapes returned by fetchone() in tests/mocks
            current_sekcja = res[0] if len(res) > 0 else None
            produkt = res[1] if len(res) > 1 else ''
            data_planu = res[2] if len(res) > 2 else None
            
            # Cannot move if already in target section
            if current_sekcja == target_sekcja:
                conn.close()
                return (False, f'Zlecenie już jest w sekcji {target_sekcja}.')
            
            # Get next sequence in target section
            cursor.execute(
                f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja=%s",
                (data_planu, target_sekcja)
            )
            res_seq = cursor.fetchone()
            next_seq = (res_seq[0] if res_seq and len(res_seq) > 0 and res_seq[0] else 0) + 1
            
            # Update plan: change section and reset sequence
            cursor.execute(
                f"UPDATE {table_plan} SET sekcja=%s, kolejnosc=%s WHERE id=%s",
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
    def shift_plan_order(plan_id, kierunek, linia='PSD'):
        """Shift a plan up or down in the queue (change order).
        
        Args:
            plan_id: ID of plan to shift
            kierunek: Direction ('up'/'w_gore'/'gora' or 'down'/'w_dol'/'dol')
            linia: Production line
            
        Returns:
            Tuple (success: bool, message: str)
        """
        try:
            # Normalize kierunek - accept 'gora'/'dol' from frontend too
            if kierunek not in ['up', 'w_gore', 'gora', 'down', 'w_dol', 'dol']:
                return (False, f'Niepoprawny kierunek: {kierunek}')
            
            is_up = kierunek in ['up', 'w_gore', 'gora']
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current plan info
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(
                f"SELECT sekcja, kolejnosc, data_planu, produkt, status FROM {table_plan} WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            
            if not res:
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            sekcja = res[0] if len(res) > 0 else None
            current_seq = res[1] if len(res) > 1 else None
            data_planu = res[2] if len(res) > 2 else None
            produkt = res[3] if len(res) > 3 else ''
            current_status = (res[4] if len(res) > 4 else 'zaplanowane')
            current_status_norm = str(current_status or '').strip().lower()

            if current_status_norm in PlanMovementService._LOCKED_STATUSES:
                conn.close()
                return (False, f"Nie można przesuwać zlecenia o statusie '{current_status}'.")

            if current_seq is None:
                conn.close()
                return (False, 'Nie można przesunąć - brak kolejności zlecenia.')
            
            # Find adjacent plan in target direction
            # For AGRO, we ignore section filter because the list is unified.
            # For PSD, we allow swapping between 'Zasyp' and 'Czyszczenie' as they are in the same view.
            sekcja_filter = ""
            params_adj = [data_planu, current_seq]
            
            if linia.upper() == 'AGRO':
                sekcja_filter = "" # No section filter for AGRO
            else:
                # For PSD and others, group Zasyp and Czyszczenie
                if sekcja.lower() in ['zasyp', 'czyszczenie']:
                    sekcja_filter = "AND LOWER(sekcja) IN ('zasyp', 'czyszczenie')"
                else:
                    sekcja_filter = "AND sekcja = %s"
                    params_adj.append(sekcja) # Append at the end to match query placeholders
            
            # 1. Renormalize first to ensure we have clean sequential numbers
            PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, sekcja if linia.upper() != 'AGRO' else None)

            # 2. Get current sequence after renormalization
            cursor.execute(f"SELECT kolejnosc FROM {table_plan} WHERE id=%s", (plan_id,))
            res_cur = cursor.fetchone()
            if not res_cur:
                conn.close()
                return (False, 'Zlecenie zniknęło po normalizacji.')
            current_seq = res_cur[0]

            # 3. Find adjacent plan (the one to swap with)
            if kierunek in ['up', 'w_gore', 'gora']:
                cursor.execute(
                    f"SELECT id, kolejnosc FROM {table_plan} "
                    f"WHERE data_planu=%s AND kolejnosc < %s {sekcja_filter} "
                    f"AND (is_deleted=0 OR is_deleted IS NULL) "
                    f"AND COALESCE(status, 'zaplanowane') NOT IN ('w toku', 'zakonczone') "
                    f"ORDER BY kolejnosc DESC LIMIT 1",
                    tuple(params_adj)
                )
            else:
                cursor.execute(
                    f"SELECT id, kolejnosc FROM {table_plan} "
                    f"WHERE data_planu=%s AND kolejnosc > %s {sekcja_filter} "
                    f"AND (is_deleted=0 OR is_deleted IS NULL) "
                    f"AND COALESCE(status, 'zaplanowane') NOT IN ('w toku', 'zakonczone') "
                    f"ORDER BY kolejnosc ASC LIMIT 1",
                    tuple(params_adj)
                )
            
            adjacent = cursor.fetchone()
            if not adjacent:
                conn.close()
                return (False, 'Zlecenie jest już na skraju listy (brak sąsiednich pozycji do zamiany).')

            adjacent_id, adjacent_seq = adjacent[0], adjacent[1]

            # 4. Swap sequences
            cursor.execute(
                f"UPDATE {table_plan} SET kolejnosc=%s WHERE id=%s",
                (adjacent_seq, plan_id)
            )
            cursor.execute(
                f"UPDATE {table_plan} SET kolejnosc=%s WHERE id=%s",
                (current_seq, adjacent_id)
            )

            # 5. Final renormalization to be sure
            PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, sekcja if linia.upper() != 'AGRO' else None)
            
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
    def reorder_plans(section, date_planu, new_order, linia='PSD'):
        """Reorder plans within a section for a specific date.
        
        Args:
            section: Section name
            date_planu: Date (YYYY-MM-DD or date object)
            new_order: List of plan IDs in desired order
            linia: Production line
            
        Returns:
            Tuple (success: bool, message: str)
        """
        conn = None
        try:
            if isinstance(date_planu, date):
                date_planu = date_planu.isoformat()
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            table_plan = get_table_name('plan_produkcji', linia)
            
            # Update each plan's sequence based on position in new_order
            # We remove the sekcja filter here to allow bulk reordering of mixed lists (e.g. Zasyp + Czyszczenie)
            for seq, plan_id in enumerate(new_order, start=1):
                cursor.execute(
                    f"UPDATE {table_plan} SET kolejnosc=%s WHERE id=%s AND data_planu=%s",
                    (seq, int(plan_id), date_planu)
                )
            
            # Renormalize to ensure no gaps or duplicates from other sections/deleted rows
            PlanMovementService.renormalize_sequences(cursor, table_plan, date_planu, section if linia.upper() != 'AGRO' else None)
            
            conn.commit()
            return (True, f'Kolejność zleceń w sekcji {section} została uporządkowana.')
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            current_app.logger.exception(f'Error reordering plans')
            return (False, f'Błąd przy zmianie kolejności: {str(e)}')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def get_plan_queue_for_section(section, date_planu, linia='PSD'):
        """Get ordered list of plans in a section for a date.
        
        Args:
            section: Section name
            date_planu: Date (YYYY-MM-DD or date object)
            linia: Production line
            
        Returns:
            List of plans ordered by kolejnosc, or empty list on error
        """
        try:
            if isinstance(date_planu, date):
                date_planu = date_planu.isoformat()
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            table_plan = get_table_name('plan_produkcji', linia)
            
            cursor.execute(f"""
                SELECT id, produkt, tonaz, status, kolejnosc, tonaz_rzeczywisty
                FROM {table_plan}
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
