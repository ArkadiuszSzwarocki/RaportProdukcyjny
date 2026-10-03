# cspell:words putaway sscc
import json
from typing import Tuple, List, Dict, Any
from app.db import get_db_connection
from app.services.magazyn_dostawy.commands.delivery_order_validator import norm_loc
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor


class DeliveryCancellationService:
    """Handles cancellation of delivery/transfer orders and restoring buffered items."""

    @classmethod
    def restore_buffered_items(cls, cursor, items: List[Dict[str, Any]], linia: str, order_ref: str, login: str) -> None:
        """Restores items moved from originalSpot to sourceSpot buffer if not accepted."""
        if not items:
            return

        for it in items:
            curr_loc = norm_loc(it.get('sourceSpot'))
            orig_loc = norm_loc(it.get('originalSpot'))
            if curr_loc and orig_loc and curr_loc != orig_loc and not (
                it.get('accepted') or it.get('rejected') or it.get('putaway_confirmed_at')
            ):
                pallet_no = it.get('sourcePalletNo') or it.get('nr_palety')
                if not pallet_no:
                    raise ValueError("Brak numeru palety do bezpiecznego cofnięcia przesunięcia")
                row, pallet_type, table = InternalTransferProcessor._find_active_pallet_by_sscc(
                    cursor, pallet_no, linia
                )
                if not row:
                    raise ValueError(f"Nie znaleziono aktywnej palety {pallet_no}")
                qty_column = 'waga_netto' if pallet_type == 'wyrob_gotowy' else 'stan_magazynowy'
                cursor.execute(
                    f"UPDATE {table} SET lokalizacja = %s WHERE id = %s AND nr_palety = %s "
                    f"AND lokalizacja = %s AND {qty_column} > 0",
                    (orig_loc, row['id'], row['nr_palety'], curr_loc)
                )
                restored = cursor.rowcount == 1

                if restored:
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'TRANSFER_CANCEL', %s, %s, %s, %s)",
                        (row['id'], row['nr_palety'], linia, pallet_type, curr_loc, orig_loc, f"Przywrócenie (anulowanie przesunięcia {order_ref})", login)
                    )

    @classmethod
    def cancel_dostawa(cls, dostawa_id: str, login: str = 'system') -> Tuple[bool, str]:
        """Cancels an order, unblocks its pallets, and restores buffered items."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT linia, status, items, order_ref FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, "Nie znaleziono przesunięcia"
            if dostawa['status'] == 'COMPLETED':
                return False, "Nie można anulować zakończonego przesunięcia"
            if dostawa['status'] == 'CANCELLED':
                return True, "Przesunięcie jest już anulowane"

            linia = dostawa['linia']
            order_ref = dostawa['order_ref']
            items = json.loads(dostawa['items'] or '[]') if isinstance(dostawa['items'], str) else (dostawa['items'] or [])

            # Restore buffered locations
            cls.restore_buffered_items(cursor, items, linia, order_ref, login)

            # Unblock pallets across all lines and tables
            pending = [item for item in items if not (
                item.get('accepted') or item.get('rejected') or item.get('putaway_confirmed_at')
            )]
            PalletLockManager.set_pallets_blocked(cursor, pending, 0, exclude_delivery_id=dostawa_id)

            # Mark as CANCELLED
            cursor.execute("UPDATE magazyn_dostawy SET status = 'CANCELLED' WHERE id = %s", (dostawa_id,))
            from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
            WarehouseOrderFulfillment.sync_transfer(cursor,dostawa_id,[item for item in items if item.get('accepted')],linia,login)
            conn.commit()
            return True, "Przesunięcie zostało anulowane (status: ANULOWANE)"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
