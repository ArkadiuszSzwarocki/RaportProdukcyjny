import json
from typing import List, Dict, Any
from app.db import get_db_connection


class WarehousePendingItemsService:
    """
    Service responsible for managing pending/in-flight items from active orders (magazyn_dostawy).
    Enriches existing physical pallets with order info and appends in-flight items without duplication.
    """

    @classmethod
    def enrich_and_append_pending(cls, items: List[Dict[str, Any]], linia: str = 'PSD') -> List[Dict[str, Any]]:
        """
        1. Identifies existing physical items in `items` by pallet ID and SSCC.
        2. Queries active orders (`magazyn_dostawy WHERE status IN ('OCZEKUJE', 'OPEN')`).
        3. If an existing pallet is part of an active order, enriches it with order metadata (PZ, MM, WZ).
        4. If a pallet from an active order does NOT exist on stock (in-flight/transferred), creates
           a virtual row with location 'OCZEKUJĄCE' and appends it to `items`.
        """
        conn = get_db_connection()
        if not conn:
            return items

        from app.blueprints.warehouse_v2.utils.date_formatters import format_date_val, compute_expiry_date
        from app.blueprints.warehouse_v2.utils.packaging_classifier import classify_packaging_type

        # Build lookup maps for physical pallets currently on stock
        existing_by_nr: Dict[str, Dict[str, Any]] = {}
        existing_by_id: Dict[str, Dict[str, Any]] = {}

        for it in items:
            nr = str(it.get('nr_palety') or it.get('displayId') or '').strip().upper()
            if nr:
                existing_by_nr[nr] = it
            pid = str(it.get('id') or '').strip()
            if pid:
                existing_by_id[pid] = it

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, supplier, order_ref, lokalizacja_z, lokalizacja_do, status, created_at, items, linia
                FROM magazyn_dostawy
                WHERE status IN ('OCZEKUJE', 'OPEN', 'W_STREFIE_PRZYJEC', 'PUTAWAY_IN_PROGRESS')
                ORDER BY id DESC
            """)
            orders = cursor.fetchall()
            target_linia = linia.upper() if linia else 'PSD'

            new_pending_items: List[Dict[str, Any]] = []

            for order in orders:
                order_linia = (order.get('linia') or 'ALL').upper()
                if target_linia != 'ALL' and order_linia != 'ALL' and order_linia != target_linia:
                    continue

                raw_items = order.get('items')
                if not raw_items:
                    continue

                try:
                    items_list = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue

                if not isinstance(items_list, list):
                    continue

                order_id_full = str(order.get('id') or '')
                order_id_short = order_id_full[:8]
                order_ref = order.get('order_ref') or f"#{order_id_short}"
                supplier = (order.get('supplier') or '').strip()
                has_supplier = bool(supplier) and supplier not in ('-', 'None', '')

                # Determine doc type: PZ (External delivery) or MM (Internal transfer)
                doc_type = 'PZ' if has_supplier else 'MM'
                order_doc_label = f"{doc_type}: #{order_id_short}"

                src_loc = (order.get('lokalizacja_z') or '').strip()
                dst_loc = (order.get('lokalizacja_do') or '').strip()

                order_status = str(order.get('status') or '').upper()

                for it in items_list:
                    if not isinstance(it, dict):
                        continue
                    if it.get('rejected'):
                        continue

                    # WMS putaway flow: keep visible until scanned putaway confirmation is done.
                    if order_status in ('W_STREFIE_PRZYJEC', 'PUTAWAY_IN_PROGRESS'):
                        if it.get('putaway_confirmed_at'):
                            continue
                    else:
                        if it.get('accepted'):
                            continue

                    nr_palety = str(it.get('nr_palety') or it.get('sourcePalletNo') or '').strip()
                    nr_upper = nr_palety.upper()
                    pallet_id = str(it.get('sourcePalletId') or it.get('id') or it.get('pallet_id') or '').strip()

                    # Source spot for this specific item
                    item_source = it.get('sourceSpot') or it.get('originalSpot') or src_loc or 'MAGAZYN'
                    item_dest = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or dst_loc or 'OCZEKUJĄCE'

                    order_meta = {
                        'order_id': order_id_full,
                        'order_ref': order_ref,
                        'order_doc_type': doc_type,
                        'order_doc_label': order_doc_label,
                        'order_supplier': supplier or 'Dostawca',
                        'order_source': item_source,
                        'order_dest': item_dest,
                        'is_pending_transfer': True
                    }

                    # Check if pallet already exists in stock
                    existing_match = (
                        (existing_by_nr.get(nr_upper) if nr_upper else None)
                        or (existing_by_id.get(pallet_id) if pallet_id else None)
                    )

                    if existing_match:
                        # Enrich existing physical pallet - DO NOT DUPLICATE!
                        existing_match.update(order_meta)
                        existing_match['has_active_order'] = True
                        # Mark as pending order
                        continue

                    # Pallet does not exist on stock (in-flight) -> create virtual pending item
                    product_name = (
                        it.get('productName')
                        or it.get('product_name')
                        or it.get('nazwa')
                        or f"Pozycja zlecenia {order_doc_label}"
                    )
                    raw_type = str(it.get('scannedType') or it.get('type') or '').lower()
                    pkg_form = str(it.get('packageForm') or '').lower()
                    if pkg_form == 'packaging' or raw_type == 'opakowanie':
                        inv_type = 'Opakowanie'
                        unit = 'szt'
                    elif raw_type == 'dodatek':
                        inv_type = 'Dodatek'
                        unit = 'kg'
                    elif raw_type in ('wyrob', 'wyrób', 'wyrob gotowy', 'wyrób gotowy'):
                        inv_type = 'Wyrób Gotowy'
                        unit = 'kg'
                    else:
                        inv_type = 'Surowiec'
                        unit = it.get('unit') or 'kg'

                    try:
                        qty = float(
                            it.get('netWeight')
                            or it.get('ilosc')
                            or it.get('quantity')
                            or it.get('unitsPerPallet')
                            or it.get('loaded_qty')
                            or it.get('stan_magazynowy')
                            or 0.0
                        )
                    except (ValueError, TypeError):
                        qty = 0.0

                    display_id = nr_palety if nr_palety else f"BUF-{pallet_id}"
                    date_prod = format_date_val(it.get('data_produkcji'))
                    date_exp = compute_expiry_date(it.get('data_przydatnosci'), it.get('data_produkcji'))
                    date_added = format_date_val(order.get('created_at'), '%Y-%m-%d %H:%M')
                    batch = it.get('nr_partii') or '-'
                    raw_pkg = it.get('packageForm') or it.get('typ_opakowania') or 'Karton'
                    pkg_type = classify_packaging_type(product_name, inv_type, qty, unit, raw_pkg)

                    row = {
                        'id': pallet_id,
                        'nr_palety': nr_palety,
                        'productName': product_name,
                        'location': 'OCZEKUJĄCE',
                        'source_location': item_source,
                        'amount': qty,
                        'type': inv_type,
                        'data_produkcji': it.get('data_produkcji'),
                        'data_przydatnosci': it.get('data_przydatnosci'),
                        'nr_partii': it.get('nr_partii'),
                        'is_blocked': 1,  # In-flight pallets are pending/blocked until putaway
                        'created_at': order.get('created_at'),
                        'typ_opakowania': raw_pkg,
                        'displayId': display_id,
                        'linia': order_linia,
                        'date_prod': date_prod,
                        'date_exp': date_exp,
                        'date_added': date_added,
                        'batch': batch,
                        'unit': unit,
                        'packaging_type': pkg_type,
                        'raw_packaging_type': raw_pkg,
                        'has_active_order': True,
                        **order_meta
                    }
                    new_pending_items.append(row)
                    if nr_upper:
                        existing_by_nr[nr_upper] = row
                    if pallet_id:
                        existing_by_id[pallet_id] = row

            # Fallback: For pallets in OCZEKUJĄCE that are not part of an active order,
            # look up their originating delivery/transfer order from magazyn_dostawy history
            unassigned_pending = [
                it for it in items
                if not it.get('order_doc_label') and (
                    'OCZEKUJ' in str(it.get('location') or '').upper() or
                    'BUFOR' in str(it.get('location') or '').upper() or
                    it.get('is_blocked')
                )
            ]

            if unassigned_pending:
                cursor.execute("""
                    SELECT id, supplier, order_ref, lokalizacja_z, lokalizacja_do, status, created_at, items
                    FROM magazyn_dostawy
                    ORDER BY id DESC
                """)
                hist_orders = cursor.fetchall()
                pallet_hist_map: Dict[str, Dict[str, Any]] = {}

                for h_order in hist_orders:
                    h_raw = h_order.get('items')
                    if not h_raw:
                        continue
                    try:
                        h_items = json.loads(h_raw) if isinstance(h_raw, str) else h_raw
                        if not isinstance(h_items, list):
                            continue
                    except Exception:
                        continue

                    h_id_full = str(h_order.get('id') or '')
                    h_id_short = h_id_full[:8]
                    h_supplier = (h_order.get('supplier') or '').strip()
                    h_has_supp = bool(h_supplier) and h_supplier not in ('-', 'None', '')
                    h_doc_type = 'PZ' if h_has_supp else 'MM'
                    h_ref = h_order.get('order_ref') or f"#{h_id_short}"
                    h_date = format_date_val(h_order.get('created_at'))
                    h_src = (h_order.get('lokalizacja_z') or '').strip()

                    for h_it in h_items:
                        if not isinstance(h_it, dict):
                            continue
                        p_nr = str(h_it.get('nr_palety') or h_it.get('sourcePalletNo') or '').strip().upper()
                        p_id = str(h_it.get('sourcePalletId') or h_it.get('id') or h_it.get('pallet_id') or '').strip()
                        it_src = h_it.get('sourceSpot') or h_it.get('originalSpot') or h_src or ('DOSTAWA' if h_has_supp else 'MAGAZYN')

                        info = {
                            'order_id': h_id_full,
                            'order_ref': h_ref,
                            'order_doc_type': h_doc_type,
                            'order_doc_label': f"{h_doc_type}: #{h_id_short}",
                            'order_supplier': h_supplier or 'Dostawca',
                            'order_source': it_src,
                            'order_date': h_date
                        }

                        if p_nr and p_nr not in pallet_hist_map:
                            pallet_hist_map[p_nr] = info
                        if p_id and p_id not in pallet_hist_map:
                            pallet_hist_map[p_id] = info

                for it in unassigned_pending:
                    p_nr = str(it.get('nr_palety') or it.get('displayId') or '').strip().upper()
                    p_id = str(it.get('id') or '').strip()
                    match = pallet_hist_map.get(p_nr) or pallet_hist_map.get(p_id)
                    if match:
                        it.update(match)

            items.extend(new_pending_items)
            return items
        except Exception as e:
            print(f"Error in WarehousePendingItemsService.enrich_and_append_pending: {e}")
            return items
        finally:
            conn.close()

    @classmethod
    def get_pending_items(cls, linia: str = 'PSD') -> List[Dict[str, Any]]:
        """Legacy helper returning only unconfirmed items from active orders."""
        res = cls.enrich_and_append_pending([], linia)
        return res
