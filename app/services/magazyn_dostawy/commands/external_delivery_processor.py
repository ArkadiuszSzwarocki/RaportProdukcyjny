from typing import List, Dict, Any
from app.db import get_table_name


class ExternalDeliveryProcessor:
    """Processes persistence and reception of external deliveries (PZ)."""

    @classmethod
    def process_reception(
        cls, cursor, items: List[Dict[str, Any]], linia: str, supplier: str,
        order_ref: str, physical_insert_loc: str, printer_info: Dict[str, Any],
        old_data: Dict[str, Any], old_items: List[Dict[str, Any]], login: str
    ) -> List[Dict[str, Any]]:
        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)

        # Cleanup deleted items upon editing existing delivery
        if old_data and old_items:
            new_pallet_ids = {it.get('sourcePalletId') for it in items if it.get('sourcePalletId')}
            for old_it in old_items:
                old_pid = old_it.get('sourcePalletId')
                if old_pid and old_pid not in new_pallet_ids and not old_it.get('accepted'):
                    old_src = str(old_it.get('source') or old_it.get('scannedType') or old_it.get('type') or '').lower()
                    del_table = table_opk if old_src == 'opakowanie' or old_it.get('packageForm') == 'packaging' else table_sur
                    try:
                        cursor.execute(f"DELETE FROM {del_table} WHERE id = %s", (old_pid,))
                    except Exception:
                        pass

        for idx, item in enumerate(items):
            if item.get('id') in (None, ''):
                item['id'] = f"item_{idx}_{int(__import__('datetime').datetime.now().timestamp())}"

            product_name = item.get('productName') or 'Brak nazwy'
            nr_palety = item.get('nr_palety')
            nr_partii = item.get('nr_partii')
            data_produkcji = item.get('data_produkcji') or None
            data_przydatnosci = item.get('data_przydatnosci') or None

            if item.get('packageForm') == 'packaging':
                qty = float(item.get('quantity') or item.get('unitsPerPallet') or 0)
                pallet_type = 'opakowanie'
                target_table = table_opk
                pkg_form = 'packaging'
            else:
                qty = float(item.get('quantity') or item.get('netWeight') or 0)
                pallet_type = 'surowiec'
                target_table = table_sur
                pkg_form = item.get('packageForm', 'bags')

            item['sourceSpot'] = 'DOSTAWA'
            item['productName'] = product_name
            item['nr_partii'] = nr_partii
            item['data_produkcji'] = str(data_produkcji) if data_produkcji else ''
            item['data_przydatnosci'] = str(data_przydatnosci) if data_przydatnosci else ''
            item['quantity'] = qty
            item['netWeight'] = qty
            item['unitsPerPallet'] = qty if pkg_form == 'packaging' else 0
            item['pallet_status'] = 'AWAITING_LABEL'

            source_pallet_id = item.get('sourcePalletId')
            if not source_pallet_id and nr_palety:
                cursor.execute(f"SELECT id FROM {target_table} WHERE nr_palety = %s LIMIT 1", (nr_palety,))
                p_exist = cursor.fetchone()
                if p_exist:
                    source_pallet_id = p_exist['id']
                    item['sourcePalletId'] = source_pallet_id

            if source_pallet_id:
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

                if nr_palety:
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'DOSTAWA_PRZYJECIE', %s, %s, %s, %s)",
                        (pallet_id, nr_palety, linia, pallet_type, 'DOSTAWA', physical_insert_loc, f"Przyjęcie zewnętrzne z {supplier} - WZ: {order_ref}", login)
                    )

        return items
