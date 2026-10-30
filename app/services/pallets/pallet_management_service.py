from flask import current_app

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name


class PalletManagementService:
    """Service handling pallet modifications: deletion, weight updates, and buffer adjustments."""

    @staticmethod
    def usun_palete(id, linia, user_login, is_ajax, safe_return_url, conn=None):
        """Delete paleta from buffer and adjust plan actual tonnage."""
        linia = str(linia).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        own_conn = False
        try:
            if conn is None:
                conn = get_db_connection()
                own_conn = True
            cursor = conn.cursor()

            cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s FOR UPDATE", (id,))
            res = cursor.fetchone()

            if not res:
                msg = f'Paleta ID={id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-DELETE] %s', msg)
                if is_ajax:
                    return ({'success': False, 'message': msg}, 404, None)
                return ('OK', 302, safe_return_url)

            plan_id = res[0]

            # Get paleta details for history before deletion
            cursor.execute(f"SELECT waga, nr_palety, status, dodal_login FROM {table_pal} WHERE id=%s", (id,))
            paleta_data = cursor.fetchone()
            waga_val = paleta_data[0] if paleta_data else 0
            nr_palety_val = paleta_data[1] if paleta_data and len(paleta_data) > 1 else None
            status_val = paleta_data[2] if paleta_data and len(paleta_data) > 2 else 'unknown'
            dodal_login_val = paleta_data[3] if paleta_data and len(paleta_data) > 3 else None

            # Get plan info for history before deletion
            cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id=%s", (plan_id,))
            plan_data = cursor.fetchone()
            plan_prod_name = plan_data[0] if plan_data and plan_data[0] else ''
            order_loc_del = f"Zlecenie #{plan_id}: {plan_prod_name}" if plan_prod_name else f"Zlecenie #{plan_id}"

            cursor.execute(f"DELETE FROM {table_pal} WHERE id=%s", (id,))
            if getattr(cursor, 'rowcount', 1) == 0:
                conn.rollback()
                msg = f'Paleta ID={id} została już usunięta'
                current_app.logger.warning('[WAREHOUSE-DELETE] %s', msg)
                if is_ajax:
                    return ({'success': False, 'message': msg}, 404, None)
                return ('OK', 302, safe_return_url)

            # Cancel any pending auto-label print job for this pallet
            try:
                job_key = f"auto-label:{linia}:{id}"
                cursor.execute(
                    "UPDATE print_jobs SET status='CANCELLED', error_message=%s, updated_at=NOW() "
                    "WHERE job_key=%s AND status='PENDING'",
                    ('Anulowano: paleta usunięta z workowania', job_key),
                )
            except Exception as pj_err:
                current_app.logger.debug('Could not cancel pending print_jobs for paleta %s: %s', id, pj_err)

            # Log to palety_historia
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, %s, 'wyrob_gotowy', 'USUNIECIE', %s, %s, %s)",
                    (id, nr_palety_val, linia, order_loc_del, f"Usunięto paletę z workowania: {nr_palety_val or 'ID='+str(id)}, waga: {waga_val} kg, status: {status_val}", user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for deleted paleta %s: %s', id, hist_err)

            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND (status IS NULL OR status != 'rezerwacja')) WHERE id = %s",
                (plan_id, plan_id),
            )

            # W linii AGRO po usunięciu palety (niebędącej rezerwacją) korygujemy start_pallet_counter,
            # aby demon paletyzatora nie potraktował zmniejszonej liczby palet w bazie jako brakującej palety do natychmiastowego dodania i wydruku.
            if linia == 'AGRO' and status_val != 'rezerwacja':
                try:
                    palletizer_cnt = 0
                    try:
                        from app.services.mqtt_service import get_latest_data
                        m_data = get_latest_data() or {}
                        palletizer_cnt = int(m_data.get('pallet_counter') or 0)
                    except Exception:
                        palletizer_cnt = 0

                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND (status IS NULL OR status != 'rezerwacja')",
                        (plan_id,),
                    )
                    rem_row = cursor.fetchone()
                    remaining_pallets = int(rem_row[0] or 0) if rem_row else 0

                    if palletizer_cnt > 0:
                        min_aligned_start = max(0, palletizer_cnt - remaining_pallets)
                        cursor.execute(
                            "UPDATE plan_produkcji_agro "
                            "SET start_pallet_counter = GREATEST(start_pallet_counter + 1, %s) "
                            "WHERE id = %s AND start_pallet_counter > 0",
                            (min_aligned_start, plan_id),
                        )
                    else:
                        cursor.execute(
                            "UPDATE plan_produkcji_agro SET start_pallet_counter = start_pallet_counter + 1 WHERE id = %s AND start_pallet_counter > 0",
                            (plan_id,),
                        )
                except Exception as spc_err:
                    current_app.logger.warning('Failed to increment start_pallet_counter on pallet deletion: %s', spc_err)

            conn.commit()

            current_app.logger.info('Usunięto paletę ID=%s, plan_id=%s, użytkownik=%s', id, plan_id, user_login)
            audit_log('Usunął paletę', f'ID={id}, plan_id={plan_id}')
            msg = 'Paleta usunięta'

            if is_ajax:
                return ({'success': True, 'message': msg}, 200, None)

        except Exception as error:
            current_app.logger.error('[WAREHOUSE-DELETE] Error deleting paleta %s: %s', id, error, exc_info=True)
            if is_ajax:
                return ({'success': False, 'message': f'Błąd: {str(error)}'}, 500, None)
        finally:
            if own_conn and conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return ('OK', 302, safe_return_url)

    @staticmethod
    def edytuj_palete(paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return_url):
        """Edit paleta weight (netto) in buffer."""
        linia = str(linia).upper()
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                waga = int(float(waga_palety.replace(',', '.')))
            except Exception:
                waga = 0

            result = update_paleta_workowanie(cursor, paleta_id, waga, linia=linia)
            if not result.get('found'):
                msg = f'Paleta ID={paleta_id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-EDIT] %s', msg)
                return ('OK', 302, safe_return_url)

            # Log to palety_historia
            try:
                old_waga = result.get('old_waga', 0)
                nr_pal = result.get('nr_palety')
                if not nr_pal:
                    t_pal = 'palety_agro' if linia == 'AGRO' else 'palety_workowanie'
                    cursor.execute(f"SELECT nr_palety FROM {t_pal} WHERE id=%s", (paleta_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        nr_pal = p_row[0] if isinstance(p_row, (list, tuple)) else p_row.get('nr_palety')
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, %s, 'wyrob_gotowy', 'EDYCJA_WAGI', %s, %s)",
                    (paleta_id, nr_pal, linia, f"Zmieniono wagę: {old_waga} kg → {waga} kg", user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for edited paleta %s: %s', paleta_id, hist_err)

            conn.commit()
            current_app.logger.info('Edytowano paletę ID=%s, waga=%s kg, użytkownik=%s', paleta_id, waga, user_login)
            audit_log('Edytował paletę', f'ID={paleta_id}, waga={waga} kg')
        except Exception as error:
            current_app.logger.error('[WAREHOUSE-EDIT] Failed to edit paleta %s: %s', paleta_id, error, exc_info=True)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return ('OK', 302, safe_return_url)
