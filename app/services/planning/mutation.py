"""Production planning service - mutation logic."""

from datetime import date, datetime, timedelta
import traceback
import logging
from flask import current_app, request, session
from app.db import get_db_connection, get_table_name, refresh_bufor_queue

class PlanningMutationService:
    """Service for mutation operations."""

    @staticmethod
    def create_plan(data_planu, produkt, tonaz, sekcja, typ_produkcji='worki_zgrzewane_25', 
                   status='zaplanowane', wymaga_oplaty=False, nazwa_zlecenia=None, typ_zlecenia=None, zasyp_id=None, linia='PSD'):
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
            
            # Normalize sekcja properly: keep specific acronyms capitalized
            if sekcja:
                s = sekcja.strip().upper()
                if s in ['PSD', 'AGRO']:
                    sekcja = s
                else:
                    sekcja = s[0].upper() + s[1:].lower() if len(s) > 0 else 'Zasyp'
            else:
                sekcja = 'Zasyp'
            
            # Determine initial status
            if wymaga_oplaty:
                initial_status = 'nieoplacone'
            else:
                initial_status = status or 'zaplanowane'
            
            table_plan = get_table_name('plan_produkcji', linia)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Prevent creating duplicate plans for same date+product
            try:
                cursor.execute(
                    f"SELECT id, sekcja FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja=%s AND (is_deleted=0 OR is_deleted IS NULL) LIMIT 1",
                    (data_planu, produkt, sekcja)
                )
                existing = cursor.fetchone()
                if existing:
                    existing_id = existing[0] if isinstance(existing, (list, tuple)) and len(existing) > 0 else existing
                    conn.close()
                    return (False, f'Istnieje już zlecenie dla produktu "{produkt}" na {data_planu}. Edytuj istniejący plan zamiast dodawać nowe.', existing_id)
            except Exception:
                # If anything goes wrong with the duplicate check, continue with insertion
                try:
                    conn.rollback()
                except Exception:
                    pass
            
            # Get next sequence number for the day
            cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s", (data_planu,))
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1
            
            # Insert new plan (include optional fields if provided)
            # bufor_agro and plan_produkcji_agro don't have 'linia' column
            if str(linia).upper() == 'AGRO':
                cursor.execute(f"""
                    INSERT INTO {table_plan} 
                    (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia, zasyp_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (data_planu, produkt, tonaz, initial_status, sekcja, nk, typ_produkcji, 0, nazwa_zlecenia or '', typ_zlecenia or '', zasyp_id))
            else:
                cursor.execute(f"""
                    INSERT INTO {table_plan} 
                    (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia, zasyp_id, linia)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (data_planu, produkt, tonaz, initial_status, sekcja, nk, typ_produkcji, 0, nazwa_zlecenia or '', typ_zlecenia or '', zasyp_id, linia))
            
            plan_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            current_app.logger.info(f'Plan created: id={plan_id}, produkt={produkt}, data={data_planu}')
            return (True, f'Plan dla {produkt} dodany.', plan_id)
            
        except Exception as e:
            current_app.logger.exception('Error creating plan')
            return (False, f'Błąd przy dodawaniu planu: {str(e)}', None)

    @staticmethod
    def delete_plan(plan_id, linia='PSD'):
        """Hard delete a plan (remove completely from database).
        
        Args:
            plan_id: ID of plan to delete
            
        Returns:
            Tuple (success: bool, message: str)
        """
        current_app.logger.debug(f'\n[SERVICE-DELETE] delete_plan({plan_id}, linia={linia}) START - HARD DELETE')
        table_plan = get_table_name('plan_produkcji', linia)
        try:
            current_app.logger.debug(f'[SERVICE-DELETE] Connecting to database...')
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if plan exists and its status
            current_app.logger.debug(f'[SERVICE-DELETE] Finding plan ID={plan_id}...')
            cursor.execute(f"SELECT status, produkt, sekcja, data_planu FROM {table_plan} WHERE id=%s", (plan_id,))
            res = cursor.fetchone()
            current_app.logger.debug(f'[SERVICE-DELETE] Result: {res}')

            if not res:
                current_app.logger.debug(f'[SERVICE-DELETE] Plan not found!')
                conn.close()
                return (False, 'Zlecenie nie istnieje.')

            status, produkt, sekcja, data_planu = res[0], res[1], res[2], res[3]
            current_app.logger.debug(f'[SERVICE-DELETE] Found plan: status={status}, produkt={produkt}, sekcja={sekcja}, data={data_planu}')
            
            # Cannot delete if in progress or completed
            if status in ['w toku', 'zakonczone']:
                current_app.logger.debug(f'[SERVICE-DELETE] Plan has protected status: {status}')
                conn.close()
                return (False, 'Nie można usunąć zlecenia w toku lub zakonczone.')
            
            # Hard delete: DELETE FROM table
            current_app.logger.debug(f'[SERVICE-DELETE] Executing DELETE...')
            cursor.execute(f"DELETE FROM {table_plan} WHERE id=%s", (plan_id,))
            current_app.logger.debug(f'[SERVICE-DELETE] DELETE finished, rowcount={cursor.rowcount}')

            # Jeśli kasujemy Zasyp, usuń też powiązane zlecenie Workowanie
            linked_deleted = 0
            if sekcja and sekcja.lower() == 'zasyp':
                cursor.execute(
                    f"DELETE FROM {table_plan} WHERE zasyp_id=%s AND status='zaplanowane'",
                    (plan_id,)
                )
                linked_deleted = cursor.rowcount

            # Renormalize sequences to close gaps
            from app.services.plan_movement_service import PlanMovementService
            PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, None if linia.upper() == 'AGRO' else sekcja)

            conn.commit()
            current_app.logger.debug(f'[SERVICE-DELETE] COMMIT success')
            conn.close()
            current_app.logger.debug(f'[SERVICE-DELETE] Connection closed')

            if linked_deleted > 0:
                current_app.logger.info(
                    f'Plan deleted (hard delete): id={plan_id}, produkt={produkt}, sekcja={sekcja}'
                    f' + {linked_deleted} linked Workowanie removed (zasyp_id cascade)'
                )
            else:
                current_app.logger.info(f'Plan deleted (hard delete): id={plan_id}, produkt={produkt}, sekcja={sekcja}')
            msg = f'Zlecenie {produkt or plan_id} zostało usunięte z planu.'
            current_app.logger.debug(f'[SERVICE-DELETE] Success: {msg}')
            return (True, msg)
            
        except Exception as e:
            current_app.logger.debug(f'[SERVICE-DELETE] EXCEPTION: {str(e)}')
            current_app.logger.debug(f'[SERVICE-DELETE] Exception type: {type(e).__name__}')
            import traceback
            current_app.logger.debug(f'[SERVICE-DELETE] Traceback: {traceback.format_exc()}')
            try:
                conn.rollback()
                current_app.logger.debug(f'[SERVICE-DELETE] ROLLBACK done')
            except Exception as rb_err:
                current_app.logger.debug(f'[SERVICE-DELETE] Rollback error: {rb_err}')
            current_app.logger.exception(f'Error deleting plan {plan_id}')
            return (False, f'Błąd przy usuwaniu: {str(e)}')

    @staticmethod
    @staticmethod
    def reschedule_plan(plan_id, nowa_data, linia='PSD'):
        """Move a plan to a different date. Also moves buffer entries if they exist.
        
        Args:
            plan_id: Plan ID to reschedule
            nowa_data: New date (YYYY-MM-DD or date object)
            
        Returns:
            (success: bool, message: str)
        """
        current_app.logger.debug(f'\n[SERVICE-RESCHEDULE] reschedule_plan({plan_id}, {nowa_data}, linia={linia}) START')
        table_plan = get_table_name('plan_produkcji', linia)
        try:
            # Convert both dates to ISO string format for safe comparison
            if hasattr(nowa_data, 'isoformat'):
                nowa_data_str = nowa_data.isoformat()
            else:
                nowa_data_str = str(nowa_data)
            
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Connecting to DB...')
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Validate plan exists and check status
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Fetching plan {plan_id}...')
            cursor.execute(
                f"SELECT id, status, data_planu, produkt, tonaz_rzeczywisty, sekcja, zasyp_id "
                f"FROM {table_plan} WHERE id=%s",
                (plan_id,)
            )
            res = cursor.fetchone()
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Result: {res}')
            
            if not res:
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] Plan not found!')
                return False, 'Plan nie istnieje.'
            
            status = res[1]
            stara_data = res[2]
            produkt = res[3]
            tonaz_rzeczywisty = res[4]
            sekcja = (res[5] or '').strip()
            parent_zasyp_id = res[6]
            
            # Convert date object to string for safe comparison
            if hasattr(stara_data, 'isoformat'):
                stara_data_str = stara_data.isoformat()
            else:
                stara_data_str = str(stara_data)
            
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Plan {plan_id}: status={status}, stara_data={stara_data_str}, produkt={produkt}, tonaz_rz={tonaz_rzeczywisty}')
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Moving from {stara_data_str} to {nowa_data_str}')
            
            # Only block if plan is currently being unpacked (w toku)
            if status == 'w toku':
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] Plan is w toku - cannot reschedule!')
                return False, 'Nie można przesunąć planu, który jest w trakcie realizacji (status: w toku).'
            
            # Additional safety: Block if already has some actual tonnage reported
            if tonaz_rzeczywisty and tonaz_rzeczywisty > 0:
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] Plan has actual tonnage ({tonaz_rzeczywisty}kg) - cannot reschedule!')
                return False, 'Nie można przesunąć zlecenia, na którym odnotowano już tonaż rzeczywisty.'
            
            # Build a set of linked plans that should move together (Zasyp + Workowanie).
            move_plan_ids = [plan_id]
            move_base_zasyp_id = plan_id if sekcja == 'Zasyp' else parent_zasyp_id

            if sekcja == 'Zasyp':
                cursor.execute(
                    f"SELECT id FROM {table_plan} "
                    f"WHERE zasyp_id=%s AND sekcja IN ('Workowanie', 'Czyszczenie') AND (is_deleted=0 OR is_deleted IS NULL)",
                    (plan_id,)
                )
                linked_work = [int(r[0]) for r in cursor.fetchall() if r and r[0]]
                move_plan_ids.extend(linked_work)
            elif sekcja in ('Workowanie', 'Czyszczenie') and parent_zasyp_id:
                move_plan_ids.append(int(parent_zasyp_id))

            # De-duplicate while keeping insertion order.
            seen = set()
            ordered_move_ids = []
            for pid in move_plan_ids:
                if pid not in seen:
                    seen.add(pid)
                    ordered_move_ids.append(pid)

            fmt_ids = ','.join(['%s'] * len(ordered_move_ids))
            cursor.execute(
                f"SELECT id, sekcja, status, tonaz_rzeczywisty FROM {table_plan} WHERE id IN ({fmt_ids})",
                tuple(ordered_move_ids)
            )
            rows = cursor.fetchall()
            plan_meta = {int(r[0]): {'sekcja': (r[1] or '').strip(), 'status': r[2], 'tonaz_rzeczywisty': r[3] or 0} for r in rows}

            # For consistency, block move if any linked plan is in progress or has already reported actual tonnage.
            for pid in ordered_move_ids:
                meta = plan_meta.get(pid)
                if not meta:
                    continue
                if meta['status'] == 'w toku':
                    return False, 'Nie można przesunąć zlecenia powiązanego ze statusem w toku.'
                if meta['tonaz_rzeczywisty'] and meta['tonaz_rzeczywisty'] > 0:
                    return False, 'Nie można przesunąć zlecenia powiązanego z odnotowanym tonażem rzeczywistym.'

            # Keep section-specific order on target day.
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Fetching section sequences for target date {nowa_data_str}...')
            cursor.execute(
                f"SELECT sekcja, MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s GROUP BY sekcja",
                (nowa_data_str,)
            )
            seq_map = {str(r[0]): (int(r[1]) if r and r[1] else 0) for r in cursor.fetchall()}

            # Move Zasyp first, then other sections to preserve intuitive ordering.
            ordered_move_ids.sort(key=lambda pid: 0 if (plan_meta.get(pid, {}).get('sekcja') == 'Zasyp') else 1)
            for pid in ordered_move_ids:
                meta = plan_meta.get(pid)
                if not meta:
                    continue
                sec = meta['sekcja'] or 'Zasyp'
                next_seq = seq_map.get(sec, 0) + 1
                seq_map[sec] = next_seq
                cursor.execute(
                    f"UPDATE {table_plan} SET data_planu=%s, kolejnosc=%s WHERE id=%s",
                    (nowa_data_str, next_seq, pid)
                )
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] Moved linked plan {pid} (sekcja={sec}) -> seq {next_seq}')
            
            # NOW HANDLE BUFFER ENTRIES (use line-specific table name)
            table_bufor = get_table_name('bufor', linia)
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] === BUFFER LOOKUP === Checking for buffer entries: zasyp_id={move_base_zasyp_id} table={table_bufor}')
            cursor.execute(f"""
                SELECT id, tonaz_rzeczywisty, spakowano, produkt, typ_produkcji
                FROM {table_bufor}
                WHERE zasyp_id=%s AND status='aktywny'
            """, (move_base_zasyp_id,))

            buffer_entries = cursor.fetchall()
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] === BUFFER RESULT === Found {len(buffer_entries)} buffer entries')
            
            if buffer_entries:
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] Found buffer entries! Moving them...')
                
                # Get max kolejka for target date in buffer (line-specific table)
                cursor.execute(
                    f"SELECT MAX(kolejka) FROM {table_bufor} WHERE data_planu=%s",
                    (nowa_data_str,)
                )
                max_buf_seq = cursor.fetchone()
                next_buf_kolejka = (max_buf_seq[0] if max_buf_seq and max_buf_seq[0] else 0) + 1
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] Buffer next kolejka: {next_buf_kolejka}')
                
                for buf_entry in buffer_entries:
                    buf_id = buf_entry[0]
                    tonaz_rz = buf_entry[1]
                    spakowano = buf_entry[2]
                    produkt_buf = buf_entry[3]
                    typ_prod = buf_entry[4]
                    
                    current_app.logger.debug(f'[SERVICE-RESCHEDULE] Moving buffer entry {buf_id}: {produkt_buf} ({tonaz_rz}kg) spakowano={spakowano}...')
                    
                    # Update buffer entry with new date and new kolejka (line-specific table)
                    cursor.execute(f"""
                        UPDATE {table_bufor}
                        SET data_planu=%s, kolejka=%s
                        WHERE id=%s
                    """, (nowa_data_str, next_buf_kolejka, buf_id))
                    
                    current_app.logger.debug(f'[SERVICE-RESCHEDULE] Buffer entry {buf_id} updated: rowcount={cursor.rowcount}')
                    next_buf_kolejka += 1
                    
                    current_app.logger.critical(
                        f'[RESCHEDULE] ✓ Moved buffer entry {buf_id}: {produkt_buf} '
                        f'from {stara_data_str} to {nowa_data_str} with {tonaz_rz}kg spakowano={spakowano}'
                    )
            else:
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] NO buffer entries found - plan has no buffer entries yet')
            
            # Commit ALL changes
            conn.commit()
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] COMMIT done')

            # Refresh buffer queue for the line so kolejki zostaną przemianowane/renumerowane
            try:
                refresh_bufor_queue(conn, linia=linia)
            except Exception as rb_err:
                current_app.logger.warning(f'[SERVICE-RESCHEDULE] refresh_bufor_queue failed: {rb_err}')

            conn.close()
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] SUCCESS - Plan moved successfully\n')
            
            if buffer_entries:
                msg = (
                    f'Przesunięto {len(ordered_move_ids)} powiązane plany oraz bufor '
                    f'({len(buffer_entries)} wpisów: {", ".join([str(e[3]) for e in buffer_entries])}).'
                )
                current_app.logger.critical(f'[RESCHEDULE-SUCCESS] {msg}')
            else:
                msg = f'Przesunięto {len(ordered_move_ids)} powiązane plany (bez wpisów w buforze).'
            
            return True, msg
            
        except Exception as e:
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] *** EXCEPTION: {str(e)}')
            current_app.logger.debug(f'[SERVICE-RESCHEDULE] Traceback: {traceback.format_exc()}')
            current_app.logger.exception(f'Error rescheduling plan {plan_id}')
            try:
                conn.rollback()
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] ROLLBACK done')
            except Exception as rb_err:
                current_app.logger.debug(f'[SERVICE-RESCHEDULE] ROLLBACK error: {rb_err}')
            return False, 'Błąd przy przesuwaniu planu.'

