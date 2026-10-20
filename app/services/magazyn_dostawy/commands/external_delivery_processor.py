from typing import List, Dict, Any
import math
from app.db import get_table_name
from app.utils.pallet_receipt_rules import ensure_unique_stock_code, validate_pallet_dates, delivery_pallet_type
from app.services.warehouse_history.movement_recorder import MovementRecorder


class ExternalDeliveryProcessor:
    """Processes persistence and reception of external deliveries (PZ)."""

    @classmethod
    def process_reception(
        cls, cursor, items: List[Dict[str, Any]], linia: str, supplier: str,
        order_ref: str, physical_insert_loc: str, printer_info: Dict[str, Any],
        old_data: Dict[str, Any], old_items: List[Dict[str, Any]], login: str,
        connection=None, delivery_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)

        old_by_id = {str(entry.get('id')): entry for entry in old_items}
        new_ids = {str(item.get('id')) for item in items}
        if any(item.get('accepted') and str(item.get('id')) not in new_ids for item in old_items):
            raise ValueError('Nie można usuwać przyjętej pozycji dostawy.')
        seen_codes = set()
        for item in items:
            old = old_by_id.get(str(item.get('id')))
            if old and old.get('accepted'):
                # Accepted stock can already be consumed; an edit must not restore its weight.
                if item != old:
                    raise ValueError('Nie można edytować przyjętej pozycji dostawy.')
                continue
            if item.get('accepted') or item.get('rejected'):
                raise ValueError('Status przyjęcia lub odrzucenia ustawia operacja odbioru, nie formularz dostawy.')
            code = str(item.get('nr_palety') or '').strip().upper()
            if code and code in seen_codes:
                raise ValueError('Ten sam kod palety występuje w dostawie kilka razy.')
            if code:
                seen_codes.add(code)
            source_id = item.get('sourcePalletId')
            if source_id and (not old or str(source_id) != str(old.get('sourcePalletId'))):
                raise ValueError('Dostawa zewnętrzna nie może nadpisywać istniejącej obcej palety.')

        # Cleanup deleted items upon editing existing delivery
        if old_data and old_items:
            new_pallet_ids = {it.get('sourcePalletId') for it in items if it.get('sourcePalletId')}
            for old_it in old_items:
                old_pid = old_it.get('sourcePalletId')
                if old_pid and old_pid not in new_pallet_ids and not old_it.get('accepted'):
                    old_type = delivery_pallet_type(old_it)
                    if old_type == 'wyrob_gotowy':
                        raise ValueError('Wyroby gotowe obsługuj przez przyjęcie z produkcji.')
                    del_table = {'surowiec': table_sur, 'opakowanie': table_opk, 'dodatek': 'magazyn_dodatki'}[old_type]
                    cursor.execute(f"SELECT id,lokalizacja,nr_palety FROM {del_table} WHERE id=%s FOR UPDATE", (old_pid,))
                    previous = cursor.fetchone()
                    if previous and (str(previous.get('lokalizacja') or '').upper() not in ('RAMPA','OCZEKUJĄCE','OCZEKUJE') or
                                     str(previous.get('nr_palety') or '') != str(old_it.get('nr_palety') or '')):
                        raise ValueError('Paleta została już odstawiona; nie można usuwać jej przez edycję dostawy.')
                    cursor.execute(f"DELETE FROM {del_table} WHERE id = %s", (old_pid,))

        for idx, item in enumerate(items):
            if item.get('accepted'):
                continue
            if item.get('id') in (None, ''):
                item['id'] = f"item_{idx}_{int(__import__('datetime').datetime.now().timestamp())}"

            product_name = item.get('productName') or 'Brak nazwy'
            nr_palety = str(item.get('nr_palety') or '').strip().upper()
            item['nr_palety'] = nr_palety
            nr_partii = item.get('nr_partii')
            data_produkcji, data_przydatnosci = validate_pallet_dates(item.get('data_produkcji'), item.get('data_przydatnosci'))

            pkg_val = str(item.get('packageForm') or '').strip().lower()
            unit_val = str(item.get('unit') or '').strip().lower()
            pallet_type = delivery_pallet_type(item)
            if pallet_type == 'wyrob_gotowy':
                raise ValueError('Wyroby gotowe przyjmuj przez przyjęcie z produkcji, nie jako surowiec dostawy.')
            is_packaging = pallet_type == 'opakowanie'
            if not is_packaging and unit_val and unit_val != 'kg':
                raise ValueError('Ilość surowca lub dodatku podaj w kg.')

            if is_packaging:
                qty = float(item.get('quantity') or item.get('unitsPerPallet') or 0)
                pallet_type = 'opakowanie'
                target_table = table_opk
                if pkg_val in ('tasma', 'taśma') or 'taśm' in product_name.lower() or 'tasm' in product_name.lower():
                    pkg_form = 'Taśma'
                elif pkg_val == 'karton':
                    pkg_form = 'Karton'
                else:
                    pkg_form = 'Opakowanie'
            else:
                qty = float(item.get('quantity') or item.get('netWeight') or 0)
                target_table = 'magazyn_dodatki' if pallet_type == 'dodatek' else table_sur
                pkg_form = item.get('packageForm', 'bags')

            if not math.isfinite(qty) or qty <= 0:
                raise ValueError('Ilość dostawy musi być dodatnia i skończona.')

            item['type'] = pallet_type
            item['scannedType'] = pallet_type
            item['sourceTable'] = target_table
            item['sourceSpot'] = 'DOSTAWA'
            item['productName'] = product_name
            item['nr_partii'] = nr_partii
            item['data_produkcji'] = str(data_produkcji) if data_produkcji else ''
            item['data_przydatnosci'] = str(data_przydatnosci) if data_przydatnosci else ''
            item['quantity'] = qty
            item['netWeight'] = qty if pallet_type != 'opakowanie' else 0
            item['unitsPerPallet'] = qty if pallet_type == 'opakowanie' else 0
            item['typ_opakowania'] = pkg_form
            item['pallet_status'] = 'AWAITING_LABEL'

            source_pallet_id = item.get('sourcePalletId')
            old = old_by_id.get(str(item.get('id')))
            if source_pallet_id and old and delivery_pallet_type(old) != pallet_type:
                raise ValueError('Nie można zmienić typu zarejestrowanej palety. Usuń pozycję roboczą i dodaj właściwą.')
            # A draft may wait for its first SSCC at the label step.
            if nr_palety:
                ensure_unique_stock_code(cursor, nr_palety,
                                         exclude=(target_table, source_pallet_id) if source_pallet_id else None,
                                         active_only=False)

            if source_pallet_id:
                cursor.execute(f"SELECT id,nr_palety,lokalizacja FROM {target_table} WHERE id=%s FOR UPDATE", (source_pallet_id,))
                previous = cursor.fetchone()
                old = old_by_id.get(str(item.get('id')))
                if not previous or not old or str(previous.get('nr_palety') or '') != str(old.get('nr_palety') or '') or str(previous.get('lokalizacja') or '').upper() not in ('RAMPA','OCZEKUJĄCE','OCZEKUJE'):
                    raise ValueError('Paleta nie jest roboczą pozycją tej dostawy.')
                if item.get('accepted'):
                    target_loc = item.get('lokalizacja_przyjecia') or item.get('targetSpot')
                    if target_loc and target_loc != 'OCZEKUJĄCE':
                        cursor.execute(
                            f"UPDATE {target_table} SET nazwa=%s, stan_magazynowy=%s, lokalizacja=%s, nr_partii=%s, data_produkcji=%s, data_przydatnosci=%s, nr_palety=%s, typ_opakowania=%s WHERE id = %s",
                            (product_name, qty, target_loc, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, source_pallet_id)
                        )
                    else:
                        cursor.execute(
                            f"UPDATE {target_table} SET nazwa=%s, stan_magazynowy=%s, nr_partii=%s, data_produkcji=%s, data_przydatnosci=%s, nr_palety=%s, typ_opakowania=%s WHERE id = %s",
                            (product_name, qty, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, source_pallet_id)
                        )
                else:
                    cursor.execute(
                        f"UPDATE {target_table} SET nazwa=%s, stan_magazynowy=%s, lokalizacja=%s, nr_partii=%s, data_produkcji=%s, data_przydatnosci=%s, nr_palety=%s, typ_opakowania=%s WHERE id = %s",
                        (product_name, qty, physical_insert_loc, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, source_pallet_id)
                    )
                pallet_id = source_pallet_id
            else:
                cursor.execute(
                    f"INSERT INTO {target_table} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (product_name, qty, physical_insert_loc, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form)
                )
                pallet_id = cursor.lastrowid
                item['sourcePalletId'] = pallet_id

            if nr_palety and not item.get('accepted'):
                operation_id = f"delivery:{delivery_id or order_ref}:item:{item.get('id')}:staging"
                history_saved = MovementRecorder.record_movement(
                    pallet_id, linia, pallet_type, 'DOSTAWA_PRZYJECIE',
                    'DOSTAWA', physical_insert_loc,
                    f"Rejestracja dostawy zewnętrznej z {supplier} - WZ: {order_ref}",
                    login, nr_palety,
                    cursor=cursor, connection=connection,
                    operation_id=operation_id,
                    quantity_before=0, quantity_after=qty,
                )
                if not history_saved:
                    raise RuntimeError("Nie udało się zapisać historii rejestracji dostawy")

        return items
