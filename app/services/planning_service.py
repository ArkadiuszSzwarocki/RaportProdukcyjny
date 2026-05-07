"""Production planning service for managing production plans."""

from datetime import date, datetime, timedelta
import traceback
from app.db import get_db_connection, get_table_name, refresh_bufor_queue
from flask import current_app, request, session
import logging


class PlanningService:
    """Service for managing production plans (creation, deletion, status changes, resumption)."""

    @staticmethod
    def _close_active_buffer_entries(update_cursor, table_bufor, zasyp_id, current_data, conn):
        """Mark source-day active buffer entries as moved for a given zasyp."""
        update_cursor.execute(
            f"UPDATE {table_bufor} SET status = 'przeniesiony' WHERE zasyp_id = %s AND DATE(data_planu) = %s AND status = 'aktywny'",
            (zasyp_id, current_data)
        )
        conn.commit()

    @staticmethod
    def _normalize_carryover_row(row):
        """Normalize carry-over source row to a dict regardless of cursor row shape."""
        if isinstance(row, dict):
            return {
                'zasyp_id': row.get('zasyp_id'),
                'produkt': row.get('produkt'),
                'typ_produkcji': row.get('typ_produkcji'),
                'z_plan': int(row.get('z_plan') or 0),
                'z_real': int(row.get('z_real') or 0),
                'workowanie_id': row.get('workowanie_id'),
                'w_plan': int(row.get('w_plan') or 0),
                'w_real': int(row.get('w_real') or 0),
            }

        return {
            'zasyp_id': row[0],
            'produkt': row[1],
            'typ_produkcji': row[2],
            'z_plan': int(row[3] or 0),
            'z_real': int(row[4] or 0),
            'workowanie_id': row[5],
            'w_plan': int(row[6] or 0),
            'w_real': int(row[7] or 0),
        }

    @staticmethod
    def _get_active_buffer_snapshot(cursor, table_bufor, zasyp_id, current_data, default_typ, default_produkt):
        """Fetch remaining buffer tonnage plus metadata for a zasyp on the source day."""
        buf_tonaz = 0
        buf_typ = default_typ
        buf_nazwa = ''
        buf_produkt = default_produkt

        try:
            cursor.execute(
                f"""
                SELECT data_planu, produkt, typ_produkcji, COALESCE(SUM(tonaz_rzeczywisty),0) AS tonaz_rzeczywisty,
                       COALESCE(SUM(spakowano),0) AS spakowano, COALESCE(MAX(nazwa_zlecenia),'') AS nazwa_zlecenia
                FROM {table_bufor}
                WHERE zasyp_id = %s AND DATE(data_planu) = %s AND status = 'aktywny'
                GROUP BY data_planu, produkt, typ_produkcji
                LIMIT 1
                """,
                (zasyp_id, current_data),
            )
            buf_row = cursor.fetchone()
        except Exception:
            buf_row = None

        if buf_row:
            if isinstance(buf_row, dict):
                buf_tonaz = int(buf_row.get('tonaz_rzeczywisty') or 0) - int(buf_row.get('spakowano') or 0)
                buf_typ = buf_row.get('typ_produkcji') or default_typ
                buf_nazwa = buf_row.get('nazwa_zlecenia')
                buf_produkt = buf_row.get('produkt')
            else:
                buf_tonaz = int(buf_row[3] or 0) - int(buf_row[4] or 0)
                buf_typ = buf_row[2] or default_typ
                buf_nazwa = buf_row[5] if len(buf_row) > 5 else ''
                buf_produkt = buf_row[1]

        return {
            'buf_tonaz': buf_tonaz,
            'buf_typ': buf_typ,
            'buf_nazwa': buf_nazwa,
            'buf_produkt': buf_produkt,
        }

    @staticmethod
    def _derive_workowanie_carryover(workowanie_remaining, buf_tonaz, produkt, typ_prod, buf_produkt, buf_typ, buf_nazwa, current_data):
        """Decide carry-over Workowanie payload based on buffer or plan shortfall."""
        if buf_tonaz > 0:
            return {
                'work_plan_amount': buf_tonaz,
                'produkt_for_new': buf_produkt,
                'typ_for_new': buf_typ,
                'nazwa_for_new': buf_nazwa or f'carry-over z {current_data}',
            }

        return {
            'work_plan_amount': workowanie_remaining,
            'produkt_for_new': produkt,
            'typ_for_new': typ_prod,
            'nazwa_for_new': f'PRZENIESIONE z {current_data}',
        }

    @staticmethod
    def _insert_carryover_buffer_entry(
        update_cursor,
        table_bufor,
        new_zasyp_id,
        next_data_str,
        produkt_for_new,
        typ_for_new,
        work_plan_amount,
        current_data,
        linia,
        conn,
    ):
        """Insert carry-over buffer entry for the next day and return sequencing info."""
        update_cursor.execute(
            f"SELECT COALESCE(MAX(kolejka), 0) FROM {table_bufor} WHERE data_planu = %s AND status = 'aktywny'",
            (next_data_str,),
        )
        max_kol = update_cursor.fetchone()[0] or 0
        if str(linia).upper() == 'AGRO':
            sql_ins = (
                f"INSERT INTO {table_bufor} (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny') ON DUPLICATE KEY UPDATE id = id"
            )
            update_cursor.execute(
                sql_ins,
                (new_zasyp_id, next_data_str, produkt_for_new, f'carry-over z {current_data}', typ_for_new, work_plan_amount, max_kol + 1),
            )
        else:
            sql_ins = (
                f"INSERT INTO {table_bufor} (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status, linia)"
                " VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'aktywny', %s) ON DUPLICATE KEY UPDATE id = id"
            )
            update_cursor.execute(
                sql_ins,
                (new_zasyp_id, next_data_str, produkt_for_new, f'carry-over z {current_data}', typ_for_new, work_plan_amount, max_kol + 1, linia),
            )
        inserted_id = update_cursor.lastrowid if hasattr(update_cursor, 'lastrowid') else None
        conn.commit()
        return {
            'max_kol': max_kol,
            'inserted_id': inserted_id,
        }

    @staticmethod
    def _normalize_existing_shortfall_work(update_cursor, existing_shortfall_work, table_plan, conn):
        """Normalize old shortfall Workowanie rows created with non-zero tonaz."""
        try:
            if isinstance(existing_shortfall_work, dict):
                existing_name = (existing_shortfall_work.get('nazwa_zlecenia') or '').upper()
                existing_tonaz = float(existing_shortfall_work.get('tonaz') or 0)
                existing_id = existing_shortfall_work.get('id')
            else:
                existing_name = ''
                existing_tonaz = 0.0
                existing_id = None

            if existing_id and 'PRZENIESIONE' in existing_name and existing_tonaz != 0:
                update_cursor.execute(
                    f"UPDATE {table_plan} SET tonaz = 0 WHERE id = %s",
                    (existing_id,),
                )
                conn.commit()
                current_app.logger.info(
                    f'[PRZENIES] Normalized existing shortfall Workowanie #{existing_id} tonaz to 0kg'
                )
                return existing_id
        except Exception:
            current_app.logger.debug('[PRZENIES] Could not normalize existing shortfall Workowanie tonaz', exc_info=True)

        return None

    @staticmethod
    def _create_ghost_zasyp_for_carryover(next_data_str, produkt_for_new, typ_prod, current_data, linia):
        """Create ghost Zasyp plan for carry-over and return its id."""
        s_z, msg_z, zasyp_created_id = PlanningService.create_plan(
            data_planu=next_data_str,
            produkt=produkt_for_new,
            tonaz=0,
            sekcja='Zasyp',
            typ_produkcji=typ_prod,
            status='zaplanowane',
            nazwa_zlecenia=f'PRZENIESIONE z {current_data}',
            typ_zlecenia='carry_over_ghost',
            linia=linia,
        )
        if isinstance(zasyp_created_id, int):
            return zasyp_created_id

        return None

    @staticmethod
    def _create_workowanie_carryover(
        next_data_str,
        produkt_for_new,
        work_plan_amount,
        typ_for_new,
        nazwa_for_new,
        new_zasyp_id,
        linia,
    ):
        """Create Workowanie carry-over linked to a ghost Zasyp and return its id."""
        s_w, msg_w, new_work_id = PlanningService.create_plan(
            data_planu=next_data_str,
            produkt=produkt_for_new,
            tonaz=work_plan_amount,
            sekcja='Workowanie',
            typ_produkcji=typ_for_new,
            status='zaplanowane',
            nazwa_zlecenia=nazwa_for_new,
            zasyp_id=new_zasyp_id,
            linia=linia,
        )
        if isinstance(new_work_id, int):
            return new_work_id

        return None

    @staticmethod
    def _handle_zasyp_shortfall(
        cursor,
        update_cursor,
        table_plan,
        table_bufor,
        next_data_str,
        produkt,
        zasyp_remaining,
        typ_prod,
        current_data,
        linia,
        zasyp_id_val,
        conn,
    ):
        """Create next-day shortfall Zasyp/Workowanie plans if needed."""
        if zasyp_remaining <= 0:
            return 0

        cursor.execute(
            f"SELECT id, COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia, COALESCE(tonaz, 0) AS tonaz FROM {table_plan} WHERE DATE(data_planu) = %s AND produkt = %s AND LOWER(sekcja) = 'workowanie' AND status = 'zaplanowane'",
            (next_data_str, produkt),
        )
        existing_shortfall_work = cursor.fetchone()
        if existing_shortfall_work:
            PlanningService._normalize_existing_shortfall_work(
                update_cursor,
                existing_shortfall_work,
                table_plan,
                conn,
            )
            current_app.logger.info(
                f'[PRZENIES] Workowanie shortfall already exists for {produkt} on {next_data_str}, skipping'
            )
            PlanningService._close_active_buffer_entries(update_cursor, table_bufor, zasyp_id_val, current_data, conn)
            return 0

        s_z2, msg_z2, zasyp_created2_id = PlanningService.create_plan(
            data_planu=next_data_str,
            produkt=produkt,
            tonaz=zasyp_remaining,
            sekcja='Zasyp',
            typ_produkcji=typ_prod,
            status='zaplanowane',
            nazwa_zlecenia=f'PRZENIESIONE ZASYP z {current_data}',
            linia=linia,
        )
        new_zasyp2_id = zasyp_created2_id if isinstance(zasyp_created2_id, int) else None

        if new_zasyp2_id:
            s_w2, msg_w2, new_work2_id = PlanningService.create_plan(
                data_planu=next_data_str,
                produkt=produkt,
                tonaz=0,
                sekcja='Workowanie',
                typ_produkcji=typ_prod,
                status='zaplanowane',
                nazwa_zlecenia=f'PRZENIESIONE z {current_data}',
                zasyp_id=new_zasyp2_id,
                linia=linia,
            )
            if isinstance(new_work2_id, int):
                conn.commit()
                current_app.logger.info(
                    f'[PRZENIES] Workowanie shortfall created/linked: {produkt} 0kg -> Workowanie #{new_work2_id} '
                    f'(Zasyp #{new_zasyp2_id})'
                )
                PlanningService._close_active_buffer_entries(update_cursor, table_bufor, zasyp_id_val, current_data, conn)
                return 1

        return 0

    @staticmethod
    def _fetch_zasyp_with_workowanie(cursor, table_plan, current_data, plan_ids_to_move=None):
        """Fetch Zasyp plans and their linked Workowanie rows for a given date."""
        if plan_ids_to_move:
            placeholders = ','.join(['%s'] * len(plan_ids_to_move))
            sql = (
                "SELECT z.id AS zasyp_id, z.produkt, z.typ_produkcji,"
                " COALESCE(z.tonaz, 0) AS z_plan,"
                " COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,"
                " w.id AS workowanie_id,"
                " COALESCE(w.tonaz, 0) AS w_plan,"
                " COALESCE(w.tonaz_rzeczywisty, 0) AS w_real"
                f" FROM {table_plan} z"
                f" LEFT JOIN {table_plan} w ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'"
                f" WHERE DATE(z.data_planu) = %s AND LOWER(z.status) IN ('zakonczone', 'zaplanowane') AND LOWER(z.sekcja) = 'zasyp' AND z.id IN ({placeholders})"
                " ORDER BY z.id"
            )
            params = tuple([current_data] + list(plan_ids_to_move))
            cursor.execute(sql, params)
        else:
            sql = (
                "SELECT z.id AS zasyp_id, z.produkt, z.typ_produkcji,"
                " COALESCE(z.tonaz, 0) AS z_plan,"
                " COALESCE(z.tonaz_rzeczywisty, 0) AS z_real,"
                " w.id AS workowanie_id,"
                " COALESCE(w.tonaz, 0) AS w_plan,"
                " COALESCE(w.tonaz_rzeczywisty, 0) AS w_real"
                f" FROM {table_plan} z"
                f" LEFT JOIN {table_plan} w ON w.zasyp_id = z.id AND LOWER(w.sekcja) = 'workowanie'"
                " WHERE DATE(z.data_planu) = %s AND LOWER(z.status) IN ('zakonczone', 'zaplanowane') AND LOWER(z.sekcja) = 'zasyp'"
                " ORDER BY z.id"
            )
            cursor.execute(sql, (current_data,))

        return cursor.fetchall()

    @staticmethod
    def _workowanie_carryover_exists(cursor, table_plan, next_data_str, produkt_for_new):
        """Check if a Workowanie carry-over already exists for the product on target date."""
        cursor.execute(
            f"SELECT id FROM {table_plan} WHERE DATE(data_planu) = %s AND produkt = %s AND LOWER(sekcja) = 'workowanie' AND status = 'zaplanowane'",
            (next_data_str, produkt_for_new),
        )
        return cursor.fetchone()

    @staticmethod
    def _process_carryover_row(
        row,
        cursor,
        update_cursor,
        table_plan,
        table_bufor,
        current_data,
        next_data_str,
        linia,
        conn,
    ):
        """Process a single Zasyp row for carry-over planning."""
        current_app.logger.debug(f"[PRZENIES-DEBUG] Processing row: {row}")
        normalized_row = PlanningService._normalize_carryover_row(row)
        produkt = normalized_row['produkt']
        typ_prod = normalized_row['typ_produkcji']
        z_plan = normalized_row['z_plan']
        z_real = normalized_row['z_real']
        w_plan = normalized_row['w_plan']
        w_real = normalized_row['w_real']

        created_delta = 0
        zasyp_remaining = max(z_plan - z_real, 0)
        workowanie_remaining = max(w_plan - w_real, 0)

        buffer_snapshot = PlanningService._get_active_buffer_snapshot(
            cursor,
            table_bufor,
            normalized_row['zasyp_id'],
            current_data,
            typ_prod,
            produkt,
        )
        buf_tonaz = buffer_snapshot['buf_tonaz']
        buf_typ = buffer_snapshot['buf_typ']
        buf_nazwa = buffer_snapshot['buf_nazwa']
        buf_produkt = buffer_snapshot['buf_produkt']

        current_app.logger.debug(
            f"[PRZENIES-DEBUG] zasyp_remaining={zasyp_remaining} workowanie_remaining={workowanie_remaining} in buffer={buf_tonaz}"
        )

        if workowanie_remaining > 0 or buf_tonaz > 0:
            carryover_payload = PlanningService._derive_workowanie_carryover(
                workowanie_remaining,
                buf_tonaz,
                produkt,
                typ_prod,
                buf_produkt,
                buf_typ,
                buf_nazwa,
                current_data,
            )
            work_plan_amount = carryover_payload['work_plan_amount']
            produkt_for_new = carryover_payload['produkt_for_new']
            typ_for_new = carryover_payload['typ_for_new']
            nazwa_for_new = carryover_payload['nazwa_for_new']

            exists = PlanningService._workowanie_carryover_exists(
                cursor,
                table_plan,
                next_data_str,
                produkt_for_new,
            )
            if exists:
                current_app.logger.info(
                    f'[PRZENIES] Carryover Workowanie already exists for {produkt_for_new} on {next_data_str}, skipping'
                )
                current_app.logger.debug(f"[PRZENIES-DEBUG] existing work row: {exists}")
                PlanningService._close_active_buffer_entries(
                    update_cursor,
                    table_bufor,
                    normalized_row['zasyp_id'],
                    current_data,
                    conn,
                )
            else:
                new_zasyp_id = PlanningService._create_ghost_zasyp_for_carryover(
                    next_data_str,
                    produkt_for_new,
                    typ_prod,
                    current_data,
                    linia,
                )
                if new_zasyp_id:
                    current_app.logger.debug(
                        f"[PRZENIES-DEBUG] Created Zasyp id={new_zasyp_id} for produkt={produkt_for_new}"
                    )
                    new_work_id = PlanningService._create_workowanie_carryover(
                        next_data_str,
                        produkt_for_new,
                        work_plan_amount,
                        typ_for_new,
                        nazwa_for_new,
                        new_zasyp_id,
                        linia,
                    )
                    if new_work_id:
                        conn.commit()
                        created_delta += 1
                        current_app.logger.info(
                            f'[PRZENIES] Workowanie carryover created/linked: {produkt_for_new} {work_plan_amount}kg -> '
                            f'Workowanie #{new_work_id} (Zasyp #{new_zasyp_id})'
                        )
                        current_app.logger.debug(
                            f"[PRZENIES-DEBUG] create_plan returned: work_id={new_work_id}"
                        )

                        buffer_insert = PlanningService._insert_carryover_buffer_entry(
                            update_cursor,
                            table_bufor,
                            new_zasyp_id,
                            next_data_str,
                            produkt_for_new,
                            typ_for_new,
                            work_plan_amount,
                            current_data,
                            linia,
                            conn,
                        )
                        current_app.logger.info(
                            f'[PRZENIES] Bufor entry inserted for {produkt_for_new} on {next_data_str} '
                            f"(kolejka {buffer_insert['max_kol'] + 1}) pointing to Zasyp #{new_zasyp_id}"
                        )
                        current_app.logger.debug(
                            f"[PRZENIES-DEBUG] bufor_inserted_id={buffer_insert['inserted_id']}"
                        )

                        PlanningService._close_active_buffer_entries(
                            update_cursor,
                            table_bufor,
                            normalized_row['zasyp_id'],
                            current_data,
                            conn,
                        )

        created_delta += PlanningService._handle_zasyp_shortfall(
            cursor,
            update_cursor,
            table_plan,
            table_bufor,
            next_data_str,
            produkt,
            zasyp_remaining,
            typ_prod,
            current_data,
            linia,
            normalized_row['zasyp_id'],
            conn,
        )

        return created_delta

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
            cursor.execute(
                f"UPDATE {table_plan} SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'",
                (sekcja,)
            )
            # Log pause of other plans (diagnostic)
            try:
                status_logger = logging.getLogger('status_changes')
                status_logger.info(f"action=pause_section sekcja={sekcja} effected_by=resume_plan caller=PlanningService.resume_plan user={session.get('login') if session else 'unknown'}")
            except Exception:
                pass

            # Set this plan to w toku (resume)
            cursor.execute(
                f"UPDATE {table_plan} SET status='w toku', real_stop=NULL WHERE id=%s",
                (plan_id,)
            )
            # Log resume event
            try:
                status_logger = logging.getLogger('status_changes')
                old_status = res[2] if len(res) > 2 else 'unknown'
                status_logger.info(f"action=resume plan_id={plan_id} old={old_status} new=w_toku user={session.get('login') if session else 'unknown'} endpoint={request.path if request else 'cli'} caller=PlanningService.resume_plan")
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
                status_logger.info(f"action=change_status plan_id={plan_id} old={old_status} new={new_status} user={session.get('login') if session else 'unknown'} endpoint={request.path if request else 'cli'} caller=PlanningService.change_status")
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
                    f"WHERE zasyp_id=%s AND sekcja='Workowanie' AND (is_deleted=0 OR is_deleted IS NULL)",
                    (plan_id,)
                )
                linked_work = [int(r[0]) for r in cursor.fetchall() if r and r[0]]
                move_plan_ids.extend(linked_work)
            elif sekcja == 'Workowanie' and parent_zasyp_id:
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
    def przenies_niezrealizowane(current_data, plan_ids_to_move=None, linia='PSD'):
        """
        Move incomplete work to next day.

        Decision basis — BUFFER (remaining to pack), not Zasyp shortfall alone:
          1. If Workowanie packed less than was zasypane → create Workowanie carryover for next day.
             A companion "ghost" Zasyp plan (already done) is created so that refresh_bufor_queue
             can auto-populate the buffer with the correct remaining amount.
          2. If Zasyp itself didn't meet its plan → also create a new Zasyp plan for next day
             (+ empty Workowanie linked to it).

        Buffer entries for the current day are NOT deleted — they persist as history.

        Args:
            current_data: Date string (YYYY-MM-DD)
            plan_ids_to_move: Optional list of Zasyp plan IDs to process (None = all)
            linia: Optional hall name specifying the table ('PSD' or 'AGRO')

        Returns:
            Tuple (success: bool, message: str, count: int)
        """
        try:
            try:
                current_date = datetime.strptime(current_data, '%Y-%m-%d').date()
            except Exception as e:
                return (False, f'Nieprawidłowy format daty: {str(e)}', 0)

            from app.db import get_table_name
            table_plan = get_table_name('plan_produkcji', linia)
            table_bufor = get_table_name('bufor', linia)

            next_date = current_date + timedelta(days=1)
            next_data_str = next_date.isoformat()

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Fetch all closed Zasyp plans for the date, with their paired Workowanie plan
            created_count = 0
            update_cursor = conn.cursor()

            rows = PlanningService._fetch_zasyp_with_workowanie(
                cursor,
                table_plan,
                current_data,
                plan_ids_to_move,
            )

            for row in rows:
                created_count += PlanningService._process_carryover_row(
                    row,
                    cursor,
                    update_cursor,
                    table_plan,
                    table_bufor,
                    current_data,
                    next_data_str,
                    linia,
                    conn,
                )

            update_cursor.close()
            conn.close()

            if created_count == 0:
                return (True, 'Brak planów do przeniesienia na następny dzień.', 0)

            product_count = created_count
            message = (
                f'✓ Przeniesiono na {next_date.strftime("%d.%m.%Y")}: '
                f'{product_count} produktów ({created_count} planów)'
            )
            current_app.logger.info(f'[PRZENIES] {message}')
            return (True, message, created_count)

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception(f'Error in przenies_niezrealizowane: {str(e)}')
            return (False, f'Błąd serwera: {str(e)}', 0)