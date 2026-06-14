"""Production planning service - buffer logic."""

from datetime import date, datetime, timedelta
import traceback
import logging
from flask import current_app, request, session
from app.db import get_db_connection, get_table_name, refresh_bufor_queue
from app.services.planning.mutation import PlanningMutationService

class PlanningBufferService:
    """Service for buffer operations."""

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
        s_z, msg_z, zasyp_created_id = PlanningMutationService.create_plan(
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
        s_w, msg_w, new_work_id = PlanningMutationService.create_plan(
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
            f"SELECT id, COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia, COALESCE(tonaz, 0) AS tonaz FROM {table_plan} WHERE DATE(data_planu) = %s AND produkt = %s AND LOWER(sekcja) IN ('workowanie', 'czyszczenie') AND status = 'zaplanowane'",
            (next_data_str, produkt),
        )
        existing_shortfall_work = cursor.fetchone()
        if existing_shortfall_work:
            PlanningBufferService._normalize_existing_shortfall_work(
                update_cursor,
                existing_shortfall_work,
                table_plan,
                conn,
            )
            current_app.logger.info(
                f'[PRZENIES] Workowanie shortfall already exists for {produkt} on {next_data_str}, skipping'
            )
            PlanningBufferService._close_active_buffer_entries(update_cursor, table_bufor, zasyp_id_val, current_data, conn)
            return 0

        s_z2, msg_z2, zasyp_created2_id = PlanningMutationService.create_plan(
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
            s_w2, msg_w2, new_work2_id = PlanningMutationService.create_plan(
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
                PlanningBufferService._close_active_buffer_entries(update_cursor, table_bufor, zasyp_id_val, current_data, conn)
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
                f" LEFT JOIN {table_plan} w ON w.zasyp_id = z.id AND LOWER(w.sekcja) IN ('workowanie', 'czyszczenie')"
                f" WHERE DATE(z.data_planu) = %s AND LOWER(z.status) IN ('zakonczone', 'zaplanowane', 'zawieszone') AND LOWER(z.sekcja) = 'zasyp' AND z.id IN ({placeholders})"
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
                f" LEFT JOIN {table_plan} w ON w.zasyp_id = z.id AND LOWER(w.sekcja) IN ('workowanie', 'czyszczenie')"
                " WHERE DATE(z.data_planu) = %s AND LOWER(z.status) IN ('zakonczone', 'zaplanowane', 'zawieszone') AND LOWER(z.sekcja) = 'zasyp'"
                " ORDER BY z.id"
            )
            cursor.execute(sql, (current_data,))

        return cursor.fetchall()

    @staticmethod
    def _workowanie_carryover_exists(cursor, table_plan, next_data_str, produkt_for_new):
        """Check if a Workowanie carry-over already exists for the product on target date."""
        cursor.execute(
            f"SELECT id FROM {table_plan} WHERE DATE(data_planu) = %s AND produkt = %s AND LOWER(sekcja) IN ('workowanie', 'czyszczenie') AND status = 'zaplanowane'",
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
        normalized_row = PlanningBufferService._normalize_carryover_row(row)
        produkt = normalized_row['produkt']
        typ_prod = normalized_row['typ_produkcji']
        z_plan = normalized_row['z_plan']
        z_real = normalized_row['z_real']
        w_plan = normalized_row['w_plan']
        w_real = normalized_row['w_real']

        created_delta = 0
        zasyp_remaining = max(z_plan - z_real, 0)
        workowanie_remaining = max(w_plan - w_real, 0)

        buffer_snapshot = PlanningBufferService._get_active_buffer_snapshot(
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
            carryover_payload = PlanningBufferService._derive_workowanie_carryover(
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

            exists = PlanningBufferService._workowanie_carryover_exists(
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
                PlanningBufferService._close_active_buffer_entries(
                    update_cursor,
                    table_bufor,
                    normalized_row['zasyp_id'],
                    current_data,
                    conn,
                )
            else:
                new_zasyp_id = PlanningBufferService._create_ghost_zasyp_for_carryover(
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
                    new_work_id = PlanningBufferService._create_workowanie_carryover(
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

                        buffer_insert = PlanningBufferService._insert_carryover_buffer_entry(
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

                        PlanningBufferService._close_active_buffer_entries(
                            update_cursor,
                            table_bufor,
                            normalized_row['zasyp_id'],
                            current_data,
                            conn,
                        )

        created_delta += PlanningBufferService._handle_zasyp_shortfall(
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

            rows = PlanningBufferService._fetch_zasyp_with_workowanie(
                cursor,
                table_plan,
                current_data,
                plan_ids_to_move,
            )

            for row in rows:
                created_count += PlanningBufferService._process_carryover_row(
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

