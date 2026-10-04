# cspell:words sscc
import json
import uuid
from datetime import datetime
from typing import Tuple, Dict, Any, List
from app.db import get_db_connection
from app.services.magazyn_dostawy.commands.delivery_order_validator import (
    norm_loc, as_bool, DeliveryOrderValidator
)
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.magazyn_dostawy.commands.external_delivery_processor import ExternalDeliveryProcessor
from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor
from app.services.magazyn_dostawy.commands.delivery_cancellation_service import DeliveryCancellationService


class DeliverySaveService:
    """Orchestrates saving and updating delivery (PZ) and internal transfer (MM) orders."""

    @classmethod
    def save_dostawa(cls, data: Dict[str, Any], login: str = 'system') -> Tuple[bool, Any]:
        linia = data.get('linia', 'PSD').upper()
        dostawa_id = data.get('id') or str(uuid.uuid4())[:18]
        order_ref = data.get('order_ref') or data.get('orderRef', '')
        supplier = data.get('supplier', '')
        delivery_date = data.get('delivery_date') or data.get('deliveryDate', datetime.now().strftime('%Y-%m-%d'))
        items = data.get('items', []) or []
        status = data.get('status', 'OCZEKUJE')
        lokalizacja_do = norm_loc(data.get('lokalizacja_do', ''))
        global_skip_lookup = as_bool(data.get('skip_warehouse_lookup', data.get('skipWarehouseLookup', False)))

        source_locations = sorted({
            norm_loc(it.get('sourceSpot'))
            for it in items
            if norm_loc(it.get('sourceSpot')) and norm_loc(it.get('sourceSpot')) != 'DOSTAWA'
        })

        is_external = bool(supplier)
        physical_insert_loc = 'RAMPA' if is_external else lokalizacja_do

        # Step 1: Validate request
        is_valid, err_msg = DeliveryOrderValidator.validate(
            data, items, is_external, lokalizacja_do, source_locations, global_skip_lookup
        )
        if not is_valid:
            return False, err_msg

        lokalizacja_z = norm_loc(data.get('lokalizacja_z', ''))
        if not lokalizacja_z:
            if source_locations:
                lokalizacja_z = source_locations[0] if len(source_locations) == 1 else 'WIELE'
            elif not is_external:
                lokalizacja_z = 'MS01' if linia == 'PSD' else ('MGW01' if linia == 'AGRO' else linia)

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, items, lokalizacja_z, supplier, linia FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
            old_data = cursor.fetchone()
            old_status = old_data['status'] if old_data else None
            if old_status in ('COMPLETED', 'CANCELLED'):
                return False, "Nie można edytować zamkniętego przesunięcia"
            old_items = json.loads(old_data['items']) if old_data and old_data.get('items') else []
            if not is_external:
                old_by_id = {str(item.get('id')): item for item in old_items}
                old_by_code = {str(item.get('nr_palety') or item.get('sourcePalletNo') or '').strip().upper(): item
                               for item in old_items if item.get('nr_palety') or item.get('sourcePalletNo')}
                refreshed = []
                included = set()
                for item in items:
                    code = str(item.get('nr_palety') or item.get('sourcePalletNo') or '').strip().upper()
                    old_item = old_by_code.get(code) if code else old_by_id.get(str(item.get('id')))
                    if old_item and (old_item.get('accepted') or old_item.get('rejected')):
                        old_code = old_item.get('sourcePalletNo') or old_item.get('nr_palety')
                        new_code = item.get('sourcePalletNo') or item.get('nr_palety')
                        if old_code != new_code:
                            return False, 'Nie można zmienić palety rozliczonej pozycji przesunięcia.'
                        item = old_item
                    elif item.get('accepted') or item.get('rejected'):
                        return False, 'Status przyjęcia palety musi być potwierdzony w odbiorze.'
                    refreshed.append(item)
                    included.add(str(item.get('id')))
                refreshed.extend(item for item in old_items if str(item.get('id')) not in included
                                 and (item.get('accepted') or item.get('rejected')))
                items = refreshed
            if old_data and (bool(old_data.get('supplier')) != is_external or str(old_data.get('linia') or linia).upper() != linia):
                return False, 'Nie można zmienić rodzaju dostawy ani magazynu przez edycję dokumentu.'
            if is_external and old_data and old_status not in ('SZKIC','OCZEKUJE'):
                return False, 'Dostawa jest już w odbiorze; edytuj ją przed awizacją.'


            # Step 1.5: Walidacja produktów z listy słownikowej
            from app.db import get_table_name
            table_sur = get_table_name('magazyn_surowce', linia)
            table_opk = get_table_name('magazyn_opakowania', linia)
            table_wg = get_table_name('magazyn_palety', linia)

            valid_dict_map = {}
            dict_queries = [
                (f"SELECT DISTINCT produkt as nazwa FROM {table_wg} WHERE produkt IS NOT NULL AND TRIM(produkt) != ''", ()),
                ("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
                ("SELECT DISTINCT nazwa FROM slownik_surowcow WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
            ]
            for dq, dparams in dict_queries:
                try:
                    cursor.execute(dq, dparams)
                    for dr in cursor.fetchall():
                        dn = (dr.get('nazwa') or '').strip()
                        if dn:
                            valid_dict_map[dn.lower()] = dn
                except Exception:
                    pass

            if items and valid_dict_map:
                for idx, it in enumerate(items):
                    p_name = str(it.get('productName') or it.get('nazwa') or '').strip()
                    if not p_name:
                        return False, f"Pozycja {idx + 1}: Brak nazwy produktu. Wybierz produkt z listy."

                    canonical = valid_dict_map.get(p_name.lower())
                    if not canonical:
                        return False, f"Pozycja {idx + 1}: Produkt '{p_name}' nie istnieje w słowniku. Wybierz poprawną nazwę z listy."
                    it['productName'] = canonical

            # Step 2: Restore removed items if editing a pending order
            if not is_external and old_status == 'OCZEKUJE' and items is not None:
                new_ids = {str(it.get('id')) for it in items}
                removed_items = [
                    old_it for old_it in old_items
                    if str(old_it.get('id')) not in new_ids and not old_it.get('accepted')
                ]
                if removed_items:
                    DeliveryCancellationService.restore_buffered_items(cursor, removed_items, linia, order_ref, login)

            # Step 3: Handle External Deliveries (PZ)
            if is_external:
                printer_id = data.get('printer_id')
                printer_info = None
                if printer_id:
                    cursor.execute("SELECT ip, nazwa FROM drukarki WHERE id = %s", (printer_id,))
                    printer_info = cursor.fetchone()

                items = ExternalDeliveryProcessor.process_reception(
                    cursor, items, linia, supplier, order_ref, physical_insert_loc,
                    printer_info, old_data, old_items, login,
                    connection=conn, delivery_id=dostawa_id,
                )

            # A row ID is local to a stock table; distinct SSCC must survive save.
            if items:
                seen_ids = set()
                deduped = []
                for it in items:
                    it_id = str(it.get('id', ''))
                    if it_id and it_id not in seen_ids:
                        seen_ids.add(it_id)
                        deduped.append(it)
                    elif not it_id:
                        deduped.append(it)
                    elif (it.get('nr_palety') or it.get('sourcePalletNo')) not in {
                        row.get('nr_palety') or row.get('sourcePalletNo') for row in deduped
                    }:
                        it['id'] = str(uuid.uuid4())
                        seen_ids.add(it['id'])
                        deduped.append(it)
                items = deduped

            # Step 5: Toggle locks for internal transfers
            if not is_external:
                if old_items:
                    PalletLockManager.set_pallets_blocked(cursor, old_items, 0, exclude_delivery_id=dostawa_id)
                if status not in ['ZAKONCZONE', 'ZAKOŃCZONE', 'ANULOWANE']:
                    PalletLockManager.set_pallets_blocked(cursor, items, 1)

            # Step 6: Handle Internal Transfers (MM)
            if not is_external:
                success, trf_res = InternalTransferProcessor.process_transfer(
                    cursor, items, linia, dostawa_id, lokalizacja_do, order_ref, global_skip_lookup, login
                )
                if not success:
                    return False, trf_res
                items = trf_res
                # Re-apply pallet blocks to resolved items
                PalletLockManager.set_pallets_blocked(cursor, items, 1)

            has_pending = any(not (it.get('accepted') or it.get('rejected')) for it in items)
            if has_pending:
                # New external deliveries use WMS 4-step workflow (SZKIC).
                # Internal transfers and updates to existing orders keep OCZEKUJE.
                if is_external:
                    final_status = old_status or 'SZKIC'
                else:
                    final_status = 'OCZEKUJE'
            else:
                final_status = 'COMPLETED' if is_external else 'OCZEKUJE'

            if old_data:
                cursor.execute("""
                    UPDATE magazyn_dostawy
                    SET order_ref=%s, supplier=%s, delivery_date=%s, status=%s, items=%s,
                        lokalizacja_z=%s, lokalizacja_do=%s
                    WHERE id=%s
                """, (order_ref, supplier, delivery_date, final_status, json.dumps(items),
                      lokalizacja_z, lokalizacja_do, dostawa_id))
            else:
                cursor.execute("""
                    INSERT INTO magazyn_dostawy
                        (id, order_ref, supplier, delivery_date, status, items,
                         created_by, created_at, requires_lab, linia,
                         lokalizacja_z, lokalizacja_do)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (dostawa_id, order_ref, supplier, delivery_date, final_status,
                      json.dumps(items), login, datetime.now(), 0, linia,
                      lokalizacja_z, lokalizacja_do))

            if not is_external:
                from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
                WarehouseOrderFulfillment.sync_transfer(cursor,dostawa_id,items,linia,login)
            conn.commit()
            return True, dostawa_id
        except ValueError as e:
            conn.rollback()
            return False, str(e)
        except Exception:
            conn.rollback()
            from flask import current_app
            current_app.logger.exception('Cannot save warehouse movement')
            return False, 'Nie udało się zapisać przesunięcia. Zachowano formularz; sprawdź zgłoszenie błędu w systemie.'
        finally:
            conn.close()
