import json
from typing import Tuple, List, Dict, Any
from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy.commands.delivery_order_validator import norm_loc
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager


class DeliveryCancellationService:
    """Handles cancellation of delivery/transfer orders and restoring buffered items."""

    @classmethod
    def restore_buffered_items(cls, cursor, items: List[Dict[str, Any]], linia: str, order_ref: str, login: str) -> None:
        """Restores items moved from originalSpot to sourceSpot buffer if not accepted."""
        if not items:
            return

        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)

        for it in items:
            curr_loc = norm_loc(it.get('sourceSpot'))
            orig_loc = norm_loc(it.get('originalSpot'))
            p_name = it.get('productName')

            if curr_loc and orig_loc and curr_loc != orig_loc and not it.get('accepted'):
                cursor.execute(
                    f"UPDATE {table_sur} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0",
                    (orig_loc, curr_loc, p_name)
                )
                restored = cursor.rowcount > 0
                if not restored:
                    cursor.execute(
                        f"UPDATE {table_opk} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0",
                        (orig_loc, curr_loc, p_name)
                    )
                    restored = cursor.rowcount > 0
                if not restored:
                    cursor.execute(
                        "UPDATE magazyn_dodatki SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0",
                        (orig_loc, curr_loc, p_name)
                    )
                    restored = cursor.rowcount > 0

                if restored:
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_CANCEL', %s, %s, %s, %s)",
                        (None, linia, 'mix', curr_loc, orig_loc, f"Przywrócenie (anulowanie przesunięcia {order_ref})", login)
                    )

    @classmethod
    def cancel_dostawa(cls, dostawa_id: str, login: str = 'system') -> Tuple[bool, str]:
        """Cancels an order, unblocks its pallets, and restores buffered items."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT linia, status, items, order_ref FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, "Nie znaleziono przesunięcia"
            if dostawa['status'] == 'COMPLETED':
                return False, "Nie można anulować zakończonego przesunięcia"

            linia = dostawa['linia']
            order_ref = dostawa['order_ref']
            items = json.loads(dostawa['items'] or '[]') if isinstance(dostawa['items'], str) else (dostawa['items'] or [])

            # Restore buffered locations
            cls.restore_buffered_items(cursor, items, linia, order_ref, login)

            # Unblock pallets across all lines and tables
            PalletLockManager.set_pallets_blocked(cursor, items, 0)

            # Mark as CANCELLED
            cursor.execute("UPDATE magazyn_dostawy SET status = 'CANCELLED' WHERE id = %s", (dostawa_id,))
            conn.commit()
            return True, "Przesunięcie zostało anulowane (status: ANULOWANE)"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
