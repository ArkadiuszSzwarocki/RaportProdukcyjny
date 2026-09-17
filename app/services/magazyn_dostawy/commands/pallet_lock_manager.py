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
