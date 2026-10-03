# cspell:words putaway
import json
import uuid
from typing import Tuple, Dict, Any
from app.db import get_db_connection
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager


class LiveTransferService:
    """Manages interactive live transfer orders (init, add, remove, close)."""

    @staticmethod
    def _read_items(dostawa):
        raw_items = dostawa.get('items')
        items = json.loads(raw_items) if isinstance(raw_items, str) else (raw_items or [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("Nieprawidłowa lista pozycji przesunięcia")
        return items

    @staticmethod
    def _is_active(dostawa):
        return str(dostawa.get('status') or '').upper() in ('OCZEKUJE', 'IN_PROGRESS', 'OPEN')

    @classmethod
    def init_live_transfer(cls, linia: str = 'AGRO', order_ref: str = None, login: str = 'system') -> Tuple[bool, Any]:
        """Initializes a new open live transfer order directly in the database."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            dostawa_id = str(uuid.uuid4())
            if not order_ref:
                from datetime import datetime
                now_s = datetime.now().strftime('%Y%m%d%H%M')
                order_ref = f"WZ-{linia.upper()}-{now_s}"

            cursor.execute("""
                INSERT INTO magazyn_dostawy
                    (id, order_ref, supplier, delivery_date, status, items,
                     created_by, created_at, requires_lab, linia,
                     lokalizacja_z, lokalizacja_do)
                VALUES (%s, %s, %s, NOW(), 'OCZEKUJE', '[]', %s, NOW(), 0, %s, 'WIELE', '')
            """, (dostawa_id, order_ref, None, login, linia.upper()))
            conn.commit()
            return True, {"dostawa_id": dostawa_id, "order_ref": order_ref}
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @classmethod
    def add_live_transfer_item(cls, dostawa_id: str, item: Dict[str, Any], linia: str = 'AGRO', login: str = 'system') -> Tuple[bool, Any]:
        """Adds a single pallet to an active live transfer order and sets is_blocked=1."""
        if not dostawa_id or not isinstance(item, dict) or not item:
            return False, "Missing dostawa_id or item payload"

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, status, items, order_ref FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            if not cls._is_active(dostawa):
                return False, "Nie można zmieniać zamkniętego przesunięcia"
            items = cls._read_items(dostawa)

            p_nr = item.get('nr_palety') or item.get('sourcePalletNo')
            p_id = item.get('sourcePalletId') or item.get('id')

            for it in items:
                it_nr = it.get('nr_palety') or it.get('sourcePalletNo')
                it_id = it.get('sourcePalletId') or it.get('id')
                if (p_nr and it_nr and str(p_nr).strip().upper() == str(it_nr).strip().upper()) or \
                   (p_id and it_id and str(p_id).strip() == str(it_id).strip()):
                    accepted_count = sum(1 for i in items if i.get('accepted'))
                    return True, {"total_items": len(items), "accepted_count": accepted_count, "items": items, "item_id": it['id']}

            item_to_add = dict(item)
            item_to_add['id'] = str(uuid.uuid4())
            item_to_add['accepted'] = False
            item_to_add['rejected'] = False
            for field in ('accepted_at', 'accepted_by', 'rejected_at', 'rejected_by',
                          'putaway_confirmed_at', 'lokalizacja_przyjecia'):
                item_to_add.pop(field, None)
            if p_nr:
                item_to_add['nr_palety'] = p_nr
                item_to_add['sourcePalletNo'] = p_nr
            if p_id:
                item_to_add['sourcePalletId'] = p_id

            items.append(item_to_add)

            # Block pallet in database
            PalletLockManager.set_pallets_blocked(cursor, [item_to_add], 1)
            from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
            WarehouseOrderFulfillment.sync_transfer(cursor,dostawa_id,items,linia,login)

            cursor.execute(
                "UPDATE magazyn_dostawy SET items = %s WHERE id = %s",
                (json.dumps(items), dostawa_id)
            )
            conn.commit()

            accepted_count = sum(1 for i in items if i.get('accepted'))
            return True, {"total_items": len(items), "accepted_count": accepted_count, "items": items, "item_id": item_to_add['id']}
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @classmethod
    def remove_live_transfer_item(cls, dostawa_id: str, item_id: str = None, nr_palety: str = None, linia: str = 'AGRO', login: str = 'system') -> Tuple[bool, Any]:
        """Removes a pallet from an active live transfer order and unblocks it."""
        if not dostawa_id:
            return False, "Missing dostawa_id"

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, items, status FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            if not cls._is_active(dostawa):
                return False, "Nie można zmieniać zamkniętego przesunięcia"
            items = cls._read_items(dostawa)

            norm_nr = str(nr_palety).strip().upper() if nr_palety else None
            norm_id = str(item_id).strip() if item_id is not None else None
            if not norm_nr and not norm_id:
                return False, "Podaj identyfikator pozycji lub numer palety"

            remaining_items = []
            removed_item = None
            for it in items:
                it_nr = str(it.get('nr_palety') or it.get('sourcePalletNo') or '').strip().upper()
                it_id = str(it.get('id') if it.get('id') is not None else '').strip()
                if (norm_id == it_id if norm_id else norm_nr == it_nr):
                    if norm_nr and norm_nr != it_nr:
                        return False, "Numer palety nie odpowiada pozycji"
                    if removed_item is not None:
                        return False, "Niejednoznaczna pozycja przesunięcia"
                    if it.get('accepted') or it.get('rejected') or it.get('putaway_confirmed_at'):
                        return False, "Nie można usunąć rozliczonej pozycji przesunięcia"
                    removed_item = it
                else:
                    remaining_items.append(it)

            if removed_item:
                PalletLockManager.set_pallets_blocked(cursor, [removed_item], 0, exclude_delivery_id=dostawa_id)
                cursor.execute(
                    "UPDATE magazyn_dostawy SET items = %s WHERE id = %s",
                    (json.dumps(remaining_items), dostawa_id)
                )
                from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
                WarehouseOrderFulfillment.sync_transfer(cursor,dostawa_id,remaining_items,linia,login)
                conn.commit()

            accepted_count = sum(1 for i in remaining_items if i.get('accepted'))
            return True, {"total_items": len(remaining_items), "accepted_count": accepted_count, "items": remaining_items}
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @classmethod
    def close_live_transfer(cls, dostawa_id: str, login: str = 'system') -> Tuple[bool, str]:
        """Closes an active live transfer order and marks status as COMPLETED."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, items, status FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, f"Transfer order #{dostawa_id} not found"

            if str(dostawa.get('status') or '').upper() == 'COMPLETED':
                return True, "Przesunięcie jest już zakończone"
            if not cls._is_active(dostawa):
                return False, "Nie można zamknąć przesunięcia w tym statusie"
            items = cls._read_items(dostawa)
            if not items or any(not (item.get('accepted') or item.get('rejected')) for item in items):
                return False, "Przyjmij lub odrzuć wszystkie pozycje przed zamknięciem przesunięcia"

            # Acceptance/rejection already handles stock and locks. Do not
            # clear a later reservation or quality block when closing history.

            cursor.execute("""
                UPDATE magazyn_dostawy
                SET status = 'COMPLETED', potwierdzone_przez = %s, potwierdzone_at = NOW()
                WHERE id = %s
            """, (login, dostawa_id))
            conn.commit()
            return True, "Zlecenie zostało pomyślnie zamknięte (status: COMPLETED)"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
