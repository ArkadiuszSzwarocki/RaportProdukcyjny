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
            # Normalize kierunek
            if kierunek not in ['up', 'w_gore', 'gora', 'down', 'w_dol', 'dol']:
                return (False, f'Niepoprawny kierunek: {kierunek}')
            
            is_up = kierunek in ['up', 'w_gore', 'gora']
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 0. Start transaction
            cursor.execute("BEGIN")
            
            # Get current plan info
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(
                f"SELECT id, sekcja, kolejnosc, data_planu, produkt, status, zasyp_id FROM {table_plan} WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            
            if not res:
                cursor.execute("ROLLBACK")
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            # Unpack fields safely
            pid = res[0]
            sekcja = res[1] or 'Zasyp'
            current_seq = res[2]
            data_planu = res[3]
            produkt = res[4] or ''
            current_status = str(res[5] or 'zaplanowane').strip().lower()
            parent_zasyp_id = res[6]

            if current_status in PlanMovementService._LOCKED_STATUSES:
                cursor.execute("ROLLBACK")
                conn.close()
                return (False, f"Nie można przesuwać zlecenia o statusie '{res[5]}'.")

            if current_seq is None:
                cursor.execute("ROLLBACK")
                conn.close()
                return (False, 'Nie można przesunąć - brak kolejności zlecenia.')

            # 1. Identify all plans that should move together (LINKED PLANS)
            # If it's a Zasyp, find its Workowanie. If it's Workowanie, find its Zasyp.
            linked_ids = [pid]
            if sekcja.lower() == 'zasyp':
                cursor.execute(
                    f"SELECT id FROM {table_plan} WHERE zasyp_id=%s AND LOWER(sekcja)='workowanie' AND (is_deleted=0 OR is_deleted IS NULL)",
                    (pid,)
                )
                linked_ids.extend([r[0] for r in cursor.fetchall()])
            elif sekcja.lower() == 'workowanie' and parent_zasyp_id:
                linked_ids.append(parent_zasyp_id)
            
            # De-duplicate
            linked_ids = list(set(linked_ids))
            
            # 2. Renormalize BEFORE shift to ensure clean sequence base
            # For simplicity, renormalize all sections that might be affected
            affected_sections = {sekcja}
            if sekcja.lower() == 'zasyp': affected_sections.add('Workowanie')
            elif sekcja.lower() == 'workowanie': affected_sections.add('Zasyp')
            
            for sec in affected_sections:
                PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, sec if linia.upper() != 'AGRO' else None)

            # 3. Perform the shift for each linked plan in its own sequence
            for move_id in linked_ids:
                # Refresh current sequence for this specific plan after renormalization
                cursor.execute(f"SELECT sekcja, kolejnosc FROM {table_plan} WHERE id=%s", (move_id,))
                m_res = cursor.fetchone()
                if not m_res: continue
                m_sekcja = m_res[0]
                m_seq = m_res[1]

                # Determine section filter for finding neighbor
                if linia.upper() == 'AGRO':
                    m_filter = ""
                    m_params = [data_planu, m_seq]
                else:
                    if m_sekcja.lower() in ['zasyp', 'czyszczenie']:
                        m_filter = "AND LOWER(sekcja) IN ('zasyp', 'czyszczenie')"
                        m_params = [data_planu, m_seq]
                    else:
                        m_filter = "AND sekcja = %s"
                        m_params = [data_planu, m_seq, m_sekcja]

                # Find neighbor
                if is_up:
                    cursor.execute(
                        f"SELECT id, kolejnosc FROM {table_plan} "
                        f"WHERE data_planu=%s AND kolejnosc < %s {m_filter} "
                        f"AND (is_deleted=0 OR is_deleted IS NULL) "
                        f"AND COALESCE(status, 'zaplanowane') NOT IN ('w toku', 'zakonczone') "
                        f"ORDER BY kolejnosc DESC LIMIT 1",
                        tuple(m_params)
                    )
                else:
                    cursor.execute(
                        f"SELECT id, kolejnosc FROM {table_plan} "
                        f"WHERE data_planu=%s AND kolejnosc > %s {m_filter} "
                        f"AND (is_deleted=0 OR is_deleted IS NULL) "
                        f"AND COALESCE(status, 'zaplanowane') NOT IN ('w toku', 'zakonczone') "
                        f"ORDER BY kolejnosc ASC LIMIT 1",
                        tuple(m_params)
                    )
                
                neighbor = cursor.fetchone()
                if neighbor:
                    neighbor_id, neighbor_seq = neighbor[0], neighbor[1]
                    # Swap
                    cursor.execute(f"UPDATE {table_plan} SET kolejnosc=%s WHERE id=%s", (neighbor_seq, move_id))
                    cursor.execute(f"UPDATE {table_plan} SET kolejnosc=%s WHERE id=%s", (m_seq, neighbor_id))

            # 4. Final renormalization
            for sec in affected_sections:
                PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, sec if linia.upper() != 'AGRO' else None)
            
            cursor.execute("COMMIT")
            conn.close()
            
            direction_label = 'w górę' if is_up else 'w dół'
            return (True, f'Zlecenie {produkt} przesunięte {direction_label}.')
            
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
                conn.close()
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
