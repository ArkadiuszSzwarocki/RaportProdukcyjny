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
                if norm_loc(row.get('lokalizacja')) == curr_loc:
                    from app.utils.location_validator import check_rack_location_availability
                    available, error = check_rack_location_availability(
                        orig_loc, current_nr_palety=row['nr_palety'],
                        product_name=row.get('nazwa') or row.get('produkt'), cursor=cursor)
                    if not available:
                        raise ValueError(error)
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
        """Cancels an order, unblocks its pallets, and restores or cleans up buffered items."""
        from flask import has_request_context, session
        from app.db import get_table_name
        from app.decorators import _normalize_role
        from app.core.hall_roles import worker_role
        from app.utils.pallet_receipt_rules import delivery_pallet_type

        raw_role = _normalize_role(session.get('rola')) if has_request_context() else ''
        is_privileged = raw_role in {'masteradmin', 'admin', 'administrator', 'lider'} or raw_role.startswith('lider') or worker_role(raw_role) in {'masteradmin', 'admin', 'lider'}

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT linia, status, items, order_ref, supplier, lokalizacja_z FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
            dostawa = cursor.fetchone()
            if not dostawa:
                return False, "Nie znaleziono przesunięcia"
            if dostawa['status'] == 'COMPLETED':
                return False, "Nie można anulować zakończonego przesunięcia"
            if dostawa['status'] == 'CANCELLED':
                return True, "Przesunięcie jest już anulowane"

            linia = dostawa['linia'] or 'PSD'
            order_ref = dostawa['order_ref']
            items = json.loads(dostawa['items'] or '[]') if isinstance(dostawa['items'], str) else (dostawa['items'] or [])

            if any(item.get('return_approval_login') for item in items) and not is_privileged:
                return False, 'Zwrot różnicy wymaga zatwierdzenia przez wydającego; nie można go anulować.'

            # Clean up unaccepted staging rows for external deliveries so cancelled orders do not leave ghost stock
            is_external = not str(dostawa.get('lokalizacja_z') or '').strip()
            if is_external:
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                staging_locations = {'RAMPA', 'OCZEKUJĄCE', 'OCZEKUJE', 'STREFA_PRZYJEC_01'}
                for it in items:
                    if it.get('accepted') or it.get('rejected') or it.get('putaway_confirmed_at'):
                        continue
                    src_pid = it.get('sourcePalletId')
                    if not src_pid:
                        continue
                    p_type = delivery_pallet_type(it)
                    if p_type == 'wyrob_gotowy':
                        continue
                    del_table = it.get('sourceTable') or {'surowiec': table_sur, 'opakowanie': table_opk, 'dodatek': 'magazyn_dodatki'}.get(p_type)
                    if del_table not in {'magazyn_surowce', 'magazyn_agro_surowce', 'magazyn_opakowania', 'magazyn_agro_opakowania', 'magazyn_dodatki'}:
                        continue
                    cursor.execute(f"SELECT id, lokalizacja, nr_palety FROM {del_table} WHERE id = %s FOR UPDATE", (src_pid,))
                    st_row = cursor.fetchone()
                    if st_row and str(st_row.get('lokalizacja') or '').strip().upper() in staging_locations:
                        expected_nr = str(it.get('nr_palety') or '').strip().upper()
                        actual_nr = str(st_row.get('nr_palety') or '').strip().upper()
                        if not expected_nr or actual_nr == expected_nr:
                            cursor.execute(f"DELETE FROM {del_table} WHERE id = %s", (src_pid,))

            # Restore buffered locations for internal transfers
            cls.restore_buffered_items(cursor, items, linia, order_ref, login)

            # Unblock pallets across all lines and tables
            pending = [
                item for item in items
                if not (item.get('accepted') or item.get('rejected') or item.get('putaway_confirmed_at'))
                and (str(item.get('sourcePalletNo') or item.get('nr_palety') or '').strip() or str(item.get('sourceTable') or '').strip())
            ]
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
