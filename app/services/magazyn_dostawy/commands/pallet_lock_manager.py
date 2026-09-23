from typing import Tuple, List, Dict, Any, Optional
from app.db import get_db_connection, get_table_name


class PalletLockManager:
    """
    Manages setting and clearing the `is_blocked` flag on pallets across warehouse tables
    (magazyn_surowce, magazyn_opakowania, magazyn_palety, magazyn_dodatki) for PSD and AGRO lines.
    """

    @classmethod
    def set_pallets_blocked(cls, cursor, items: List[Dict[str, Any]], blocked_val: int = 1) -> None:
        """Sets is_blocked to blocked_val (1 or 0) for all pallets in items."""
        if not items:
            return

        for it in items:
            pid = it.get('sourcePalletId') or it.get('id')
            pnr = it.get('sourcePalletNo') or it.get('nr_palety')
            if not pid and not pnr:
                continue

            for l_code in ['PSD', 'AGRO']:
                for tbl in [
                    get_table_name('magazyn_surowce', l_code),
                    get_table_name('magazyn_opakowania', l_code),
                    get_table_name('magazyn_palety', l_code)
                ]:
                    if pid:
                        try:
                            cursor.execute(f"UPDATE {tbl} SET is_blocked = %s WHERE id = %s", (blocked_val, pid))
                        except Exception:
                            pass
                    if pnr:
                        try:
                            cursor.execute(f"UPDATE {tbl} SET is_blocked = %s WHERE nr_palety = %s", (blocked_val, pnr))
                        except Exception:
                            pass

                if pid:
                    try:
                        cursor.execute("UPDATE magazyn_dodatki SET is_blocked = %s WHERE id = %s", (blocked_val, pid))
                    except Exception:
                        pass
                if pnr:
                    try:
                        cursor.execute("UPDATE magazyn_dodatki SET is_blocked = %s WHERE nr_palety = %s", (blocked_val, pnr))
                    except Exception:
                        pass

    @classmethod
    def lock_draft_pallets(cls, items: List[Dict[str, Any]], linia: str = 'AGRO', user_login: str = 'system') -> Tuple[bool, str]:
        """Locks pallets added to a draft transfer list."""
        if not items:
            return True, "No items to lock"

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cls.set_pallets_blocked(cursor, items, 1)
            conn.commit()
            return True, "Draft pallets locked successfully"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @classmethod
    def unlock_draft_pallets(cls, items: List[Dict[str, Any]], linia: str = 'AGRO', user_login: str = 'system') -> Tuple[bool, str]:
        """Unlocks pallets removed from a draft transfer list if not in an active transfer."""
        if not items:
            return True, "No items to unlock"

        from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            eligible_items = []
            for it in items:
                pid = it.get('sourcePalletId') or it.get('id')
                pnr = it.get('sourcePalletNo') or it.get('nr_palety')
                if not pid and not pnr:
                    continue

                in_trf, _ = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=pid, nr_palety=pnr)
                if not in_trf:
                    eligible_items.append(it)

            if eligible_items:
                cls.set_pallets_blocked(cursor, eligible_items, 0)
                conn.commit()
            return True, "Draft pallets unlocked successfully"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @classmethod
    def reconcile_orphan_transfer_locks(cls, cursor=None) -> int:
        """
        Reconciles orphaned pallet locks:
        Pallets marked as is_blocked = 1 that are NOT part of any active in-flight transfer
        (status IN ('OCZEKUJE', 'OPEN', 'W_STREFIE_PRZYJEC', 'PUTAWAY_IN_PROGRESS'))
        and were NOT manually blocked by quality/user are unblocked (is_blocked = 0).
        """
        import json
        should_close = False
        conn = None
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            should_close = True

        try:
            # 1. Collect all active in-flight pallet IDs and numbers from active orders
            cursor.execute("""
                SELECT items FROM magazyn_dostawy 
                WHERE status IN ('OCZEKUJE', 'OPEN', 'W_STREFIE_PRZYJEC', 'PUTAWAY_IN_PROGRESS')
            """)
            active_orders = cursor.fetchall()
            active_pids = set()
            active_pnrs = set()

            for ord_row in active_orders:
                raw_items = ord_row.get('items')
                if not raw_items:
                    continue
                try:
                    items_list = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue
                if not isinstance(items_list, list):
                    continue
                for it in items_list:
                    if not isinstance(it, dict) or it.get('accepted') or it.get('rejected'):
                        continue
                    if it.get('id'):
                        active_pids.add(str(it['id']))
                    if it.get('sourcePalletId'):
                        active_pids.add(str(it['sourcePalletId']))
                    if it.get('nr_palety'):
                        active_pnrs.add(str(it['nr_palety']).strip().upper())
                    if it.get('sourcePalletNo'):
                        active_pnrs.add(str(it['sourcePalletNo']).strip().upper())

            # 2. Collect manually blocked pallets from history (where latest action is BLOKADA)
            cursor.execute("""
                SELECT h.nr_palety, h.paleta_id, h.akcja
                FROM palety_historia h
                INNER JOIN (
                    SELECT COALESCE(NULLIF(TRIM(nr_palety), ''), CAST(paleta_id AS CHAR)) as p_ref, MAX(id) as max_id
                    FROM palety_historia
                    WHERE akcja IN ('BLOKADA', 'ODBLOKOWANIE', 'BLOKADA_MANUALNA')
                      AND (nr_palety IS NOT NULL OR paleta_id IS NOT NULL)
                    GROUP BY COALESCE(NULLIF(TRIM(nr_palety), ''), CAST(paleta_id AS CHAR))
                ) last_h ON h.id = last_h.max_id
                WHERE h.akcja IN ('BLOKADA', 'BLOKADA_MANUALNA')
            """)
            manual_blocked_rows = cursor.fetchall()
            manual_blocked_nrs = {str(r['nr_palety']).strip().upper() for r in manual_blocked_rows if r.get('nr_palety')}
            manual_blocked_ids = {str(r['paleta_id']).strip() for r in manual_blocked_rows if r.get('paleta_id')}

            unblocked_count = 0

            # 3. Scan all warehouse stock tables for is_blocked = 1
            all_tables = [
                'magazyn_surowce',
                'magazyn_opakowania',
                'magazyn_palety',
                'magazyn_palety_agro',
                'magazyn_dodatki'
            ]

            for tbl in all_tables:
                try:
                    cursor.execute(f"SELECT id, nr_palety FROM {tbl} WHERE is_blocked = 1")
                    blocked_items = cursor.fetchall()
                    for b_item in blocked_items:
                        b_id = str(b_item.get('id') or '')
                        b_nr = str(b_item.get('nr_palety') or '').strip().upper()

                        # Check if in active in-flight transfer
                        if (b_id and b_id in active_pids) or (b_nr and b_nr in active_pnrs):
                            continue

                        # Check if manually blocked
                        if (b_nr and b_nr in manual_blocked_nrs) or (b_id and b_id in manual_blocked_ids):
                            continue

                        # Otherwise, it's an orphaned transfer lock -> unblock it!
                        cursor.execute(f"UPDATE {tbl} SET is_blocked = 0 WHERE id = %s", (b_item['id'],))
                        unblocked_count += 1
                except Exception as tbl_err:
                    continue

            if conn:
                conn.commit()

            return unblocked_count
        except Exception as err:
            print(f"Error reconciling orphan transfer locks: {err}")
            return 0
        finally:
            if should_close and conn:
                conn.close()
