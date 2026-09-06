from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy.location_service import LocationService
import json
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

class DeliveryQueries:

    def get_dostawy(linia='PSD'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                if str(linia).upper() == 'ALL':
                    cursor.execute("SELECT * FROM magazyn_dostawy ORDER BY created_at DESC")
                else:
                    cursor.execute(
                        "SELECT * FROM magazyn_dostawy WHERE UPPER(linia) = %s ORDER BY created_at DESC",
                        (str(linia).upper(),)
                    )
                dostawy = cursor.fetchall()
                for d in dostawy:
                    if d.get('items'):
                        try:
                            d['items_parsed'] = json.loads(d['items'])
                        except Exception:
                            d['items_parsed'] = []
                return dostawy
            finally:
                conn.close()

    def get_oczekujace(linia='PSD'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                # 1. Pending Raw Materials / Transfers
                if str(linia).upper() == 'ALL':
                    cursor.execute(
                        "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' ORDER BY created_at DESC"
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' AND UPPER(linia) = %s ORDER BY created_at DESC",
                        (str(linia).upper(),)
                    )
                dostawy = cursor.fetchall()
                for d in dostawy:
                    if d.get('items'):
                        try: d['items_parsed'] = json.loads(d['items'])
                        except Exception: d['items_parsed'] = []
                
                # 2. Pending Production Pallets (WG)
                wg = DeliveryQueries.get_pending_production_pallets(linia)
                
                try:
                    DeliveryQueries.sync_pending_transfers_blocked_state()
                except Exception:
                    pass

                return {
                    "dostawy": dostawy,
                    "wg": wg
                }
            finally:
                conn.close()

    def get_pending_production_pallets(linia='PSD'):
            """Fetches pallets with status 'do_przyjecia' from production tables."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                normalized_line = str(linia or 'PSD').upper()
                
                # Uniwersalny skaner - pobieraj ze wszystkich linii
                if normalized_line == 'ALL':
                    all_pallets = []
                    for line in ['PSD', 'AGRO']:
                        try:
                            line_pallets = DeliveryQueries._get_pending_production_for_line(cursor, line)
                            all_pallets.extend(line_pallets)
                        except Exception as e:
                            print(f"Error fetching pending production pallets for {line}: {e}")
                    return all_pallets
                else:
                    return DeliveryQueries._get_pending_production_for_line(cursor, normalized_line)
            except Exception as e:
                print(f"Error fetching pending production pallets: {e}")
                return []
            finally:
                conn.close()

    @staticmethod
    def _get_pending_production_for_line(cursor, linia='PSD'):
            """Helper function to get pending production pallets for a specific line."""
            normalized_line = str(linia or 'PSD').upper()
            is_psd = normalized_line == 'PSD'
            table_prod = 'palety_workowanie' if is_psd else 'palety_agro'
            table_plan = 'plan_produkcji' if is_psd else 'plan_produkcji_agro'
            table_wh = 'magazyn_palety' if is_psd else 'magazyn_palety_agro'
            plan_product_col = 'plan.produkt'
            
            # Check if table exists (safety)
            cursor.execute("SHOW TABLES LIKE %s", (table_prod,))
            if not cursor.fetchone():
                return []

            cursor.execute("SHOW TABLES LIKE %s", (table_wh,))
            has_wh_table = bool(cursor.fetchone())

            suggested_location_sql = "''"
            if has_wh_table:
                suggested_location_sql = (
                    f"COALESCE((SELECT w.lokalizacja FROM {table_wh} w "
                    f"WHERE w.produkt = {plan_product_col} "
                    "AND w.lokalizacja IS NOT NULL AND w.lokalizacja <> '' "
                    "ORDER BY COALESCE(w.data_potwierdzenia, w.created_at, w.id) DESC LIMIT 1), '')"
                )

            query = f"""
                SELECT p.*, plan.produkt as nazwa_produktu, 
                       plan.nazwa_zlecenia as numer_zlecenia,
                       {suggested_location_sql} AS suggested_location
                FROM {table_prod} p
                LEFT JOIN {table_plan} plan ON p.plan_id = plan.id
                WHERE p.status = 'do_przyjecia'
                ORDER BY p.data_dodania DESC
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                suggested_location = LocationService._normalize_location_code(row.get('suggested_location'))
                row['suggested_location'] = suggested_location
                row['target_zone'] = LocationService._derive_target_zone(suggested_location)
                row['linia'] = normalized_line
            return rows

    def get_raport(date_from=None, date_to=None):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                query = "SELECT * FROM magazyn_dostawy WHERE status = 'COMPLETED'"
                params = []
                if date_from:
                    query += " AND DATE(created_at) >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND DATE(created_at) <= %s"
                    params.append(date_to)
                query += " ORDER BY created_at DESC"
                cursor.execute(query, params)
                dostawy = cursor.fetchall()
                
                # For backfilling missing nr_palety in old reports
                table_sur_psd = get_table_name('magazyn_surowce', 'PSD')
                table_opk_psd = get_table_name('magazyn_opakowania', 'PSD')
                table_sur_agro = get_table_name('magazyn_surowce', 'AGRO')
                table_opk_agro = get_table_name('magazyn_opakowania', 'AGRO')

                for d in dostawy:
                    if d.get('created_at'):
                        d['created_at'] = d['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                    if d.get('potwierdzone_at'):
                        d['potwierdzone_at'] = d['potwierdzone_at'].strftime('%Y-%m-%d %H:%M:%S')
                    if d.get('items'):
                        try:
                            its = json.loads(d['items'])
                            linia = d.get('linia', 'PSD').upper()
                            t_sur = table_sur_agro if linia == 'AGRO' else table_sur_psd
                            t_opk = table_opk_agro if linia == 'AGRO' else table_opk_psd

                            for item in its:
                                if not item.get('nr_palety'):
                                    # Try to find it in DB by last known location/product
                                    loc = item.get('lokalizacja_przyjecia')
                                    name = item.get('productName')
                                    if loc and name:
                                        cursor.execute(f"SELECT nr_palety FROM {t_sur} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (loc, name))
                                        res = cursor.fetchone()
                                        if not res:
                                            cursor.execute(f"SELECT nr_palety FROM {t_opk} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (loc, name))
                                            res = cursor.fetchone()
                                        if res:
                                            item['nr_palety'] = res['nr_palety']
                            d['items_parsed'] = its
                        except Exception as e:
                            print(f"Error parsing items in raport: {e}")
                            d['items_parsed'] = []
                return dostawy
            finally:
                conn.close()

    @staticmethod
    def is_pallet_in_pending_transfer(pallet_id=None, nr_palety=None):
        """
        Sprawdza czy paleta o podanym ID lub numerze znajduje się w otwartym zleceniu przesunięcia (status 'OCZEKUJE').
        Zwraca tuple (is_in_transfer: bool, order_ref: str).
        """
        if not pallet_id and not nr_palety:
            return False, ""

        norm_nr = str(nr_palety).strip().upper() if nr_palety else ""
        norm_id = str(pallet_id).strip() if pallet_id else ""

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, order_ref, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE'")
            rows = cursor.fetchall()
            for r in rows:
                raw_items = r.get('items')
                if not raw_items:
                    continue
                try:
                    items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue
                if not isinstance(items, list):
                    continue
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    if it.get('accepted') or it.get('rejected'):
                        continue
                    it_nr = str(it.get('nr_palety') or it.get('sourcePalletNo') or '').strip().upper()
                    it_ids = [str(val).strip() for val in [it.get('sourcePalletId'), it.get('id'), it.get('surowiec_id'), it.get('pallet_id')] if val is not None and str(val).strip()]
                    if (norm_nr and it_nr and norm_nr == it_nr) or (norm_id and norm_id in it_ids):
                        ref = r.get('order_ref') or f"RUCH-{r['id'][:8]}"
                        return True, ref
            return False, ""
        except Exception as e:
            print(f"Error checking pending transfer for pallet: {e}")
            return False, ""
        finally:
            conn.close()

    @staticmethod
    def sync_pending_transfers_blocked_state():
        """
        Synchronizuje flagę is_blocked = 1 dla wszystkich palet znajdujących się na aktywnych listach przesunięć.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE'")
            rows = cursor.fetchall()
            for r in rows:
                raw_items = r.get('items')
                if not raw_items:
                    continue
                try:
                    items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue
                if not isinstance(items, list):
                    continue
                for it in items:
                    if not isinstance(it, dict) or it.get('accepted') or it.get('rejected'):
                        continue
                    pid = it.get('sourcePalletId')
                    pnr = it.get('nr_palety') or it.get('sourcePalletNo')
                    for l_code in ['PSD', 'AGRO']:
                        for tbl in [get_table_name('magazyn_surowce', l_code), get_table_name('magazyn_opakowania', l_code), get_table_name('magazyn_palety', l_code)]:
                            if pid:
                                try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 1 WHERE id = %s", (pid,))
                                except Exception: pass
                            if pnr:
                                try: cursor.execute(f"UPDATE {tbl} SET is_blocked = 1 WHERE nr_palety = %s", (pnr,))
                                except Exception: pass
                        if pid:
                            try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1 WHERE id = %s", (pid,))
                            except Exception: pass
                        if pnr:
                            try: cursor.execute("UPDATE magazyn_dodatki SET is_blocked = 1 WHERE nr_palety = %s", (pnr,))
                            except Exception: pass
            conn.commit()
        except Exception as e:
            print(f"Error syncing pending transfers blocked state: {e}")
        finally:
            conn.close()

    @staticmethod
    def get_live_transfer_status(dostawa_id):
        """Returns live execution status, accepted items count, and completion state for an active transfer order."""
        if not dostawa_id:
            return False, "Missing dostawa_id"
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, order_ref, status, linia, created_at, created_by,
                       potwierdzone_przez, potwierdzone_at, items
                FROM magazyn_dostawy
                WHERE id = %s
            """, (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            raw_items = dostawa.get('items')
            items = json.loads(raw_items) if isinstance(raw_items, str) else (raw_items or [])
            if not isinstance(items, list):
                items = []

            total_items = len(items)
            accepted_count = sum(1 for it in items if it.get('accepted'))
            all_accepted = total_items > 0 and (accepted_count == total_items)
            
            # If all items are accepted and status is still OCZEKUJE, update it to COMPLETED
            if all_accepted and dostawa.get('status') == 'OCZEKUJE':
                cursor.execute("""
                    UPDATE magazyn_dostawy
                    SET status = 'COMPLETED', potwierdzone_at = NOW()
                    WHERE id = %s
                """, (dostawa_id,))
                conn.commit()
                dostawa['status'] = 'COMPLETED'

            return True, {
                "dostawa_id": dostawa['id'],
                "order_ref": dostawa.get('order_ref') or '',
                "status": dostawa.get('status') or 'OCZEKUJE',
                "linia": dostawa.get('linia') or 'AGRO',
                "total_items": total_items,
                "accepted_count": accepted_count,
                "all_accepted": all_accepted,
                "items": items,
            }
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

