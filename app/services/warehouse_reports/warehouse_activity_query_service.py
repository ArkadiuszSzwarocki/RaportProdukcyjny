"""
Moduł odpowiedzialny za odczyt i agregację danych magazynowych do raportów dziennych (CQRS: Query).
"""
from typing import Dict, Any, List, Tuple
import json
import re
from app.db import get_db_connection
from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier
from app.services.warehouse_reports.warehouse_status_resolver import WarehouseStatusResolver


class WarehouseActivityQueryService:
    @staticmethod
    def extract_item_qty(item: Dict[str, Any]) -> float:
        """Pobiera ilość lub wagę z pozycji niezależnie od klucza w JSON."""
        for k in ('netWeight', 'currentWeight', 'weight', 'waga_netto', 'waga', 'stan_magazynowy'):
            val = item.get(k)
            if val not in (None, '', 0, '0'):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass

        for k in ('quantity', 'unitsPerPallet', 'ilosc', 'loaded_qty', 'requested_qty'):
            val = item.get(k)
            if val not in (None, '', 0, '0'):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
        return 0.0

    @classmethod
    def get_daily_warehouse_activity(cls, date_str: str) -> Dict[str, Any]:
        """Pobiera wszystkie zrealizowane lub zarejestrowane w danym dniu dostawy zewnętrzne oraz przesunięcia MM / transfery."""
        conn = get_db_connection()
        dostawy_rows = []
        osip_transfers_rows = []
        osip_items_by_transfer = {}
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM magazyn_dostawy 
                WHERE status = 'COMPLETED' 
                  AND (
                      DATE(potwierdzone_at) = %s 
                      OR (potwierdzone_at IS NULL AND DATE(created_at) = %s)
                      OR (potwierdzone_at IS NULL AND delivery_date = %s)
                  )
                ORDER BY created_at ASC
            """, (date_str, date_str, date_str))
            dostawy_rows = cursor.fetchall() or []

            try:
                cursor.execute("""
                    SELECT * FROM osip_transfers 
                    WHERE status = 'COMPLETED'
                      AND (
                          DATE(completed_at) = %s 
                          OR (completed_at IS NULL AND DATE(created_at) = %s)
                      )
                    ORDER BY created_at ASC
                """, (date_str, date_str))
                osip_transfers_rows = cursor.fetchall() or []

                if osip_transfers_rows:
                    t_ids = [t['id'] for t in osip_transfers_rows]
                    placeholders = ','.join(['%s'] * len(t_ids))
                    cursor.execute(f"""
                        SELECT * FROM osip_transfer_items 
                        WHERE transfer_id IN ({placeholders})
                        ORDER BY id ASC
                    """, tuple(t_ids))
                    all_it_rows = cursor.fetchall() or []
                    for it in all_it_rows:
                        tid = it['transfer_id']
                        if tid not in osip_items_by_transfer:
                            osip_items_by_transfer[tid] = []
                        osip_items_by_transfer[tid].append(it)
            except Exception:
                osip_transfers_rows = []
            finally:
                cursor.close()
        finally:
            conn.close()

        deliveries_wz = []
        deliveries_centrala = []
        transfers_mm = []
        all_documents = []

        deliveries_wz_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        deliveries_centrala_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        transfers_mm_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        all_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        total_pallets = 0
        total_qty_by_unit: Dict[str, float] = {}

        for d in dostawy_rows:
            try:
                raw_items = json.loads(d.get('items') or '[]')
            except Exception:
                raw_items = []

            if WarehouseDocumentClassifier.is_production_movement(d, raw_items):
                continue
            if WarehouseDocumentClassifier.is_internal_mp01_movement(d, raw_items):
                continue

            cat = WarehouseDocumentClassifier.categorize_delivery_doc(d, raw_items)
            supplier_val = str(d.get('supplier') or '').strip()
            supplier_upper = supplier_val.upper()
            src_upper = str(d.get('lokalizacja_z') or '').strip().upper()
            ref_val = cat['ref']
            clean_ref = re.sub(r'[\s/\\:*?"<>|]+', '_', str(ref_val)).strip('_')

            if not cat['is_external']:
                doc_category = 'PRZESUNIECIE_MM'
                doc_category_title = 'Przesunięcie MM'
                pdf_filename = f"Przesuniecie_MM_{clean_ref}.pdf"
            elif supplier_upper in ('CENTRALA', 'MAGAZYN CENTRALA', 'MAGAZYN CENTRALNY') or src_upper in ('CENTRALA', 'MAGAZYN CENTRALA'):
                doc_category = 'DOSTAWA_CENTRALA'
                doc_category_title = 'Dostawa Centrala'
                pdf_filename = f"Dostawa_Centrala_{clean_ref}.pdf"
            elif cat['doc_type_code'] == 'DOSTAWA_CENTRALA':
                if not supplier_val or supplier_upper in ('CENTRALA', 'MAGAZYN CENTRALA', 'MAGAZYN CENTRALNY'):
                    doc_category = 'DOSTAWA_CENTRALA'
                    doc_category_title = 'Dostawa Centrala'
                    pdf_filename = f"Dostawa_Centrala_{clean_ref}.pdf"
                else:
                    doc_category = 'DOSTAWA_ZEWNETRZNA'
                    doc_category_title = 'Dostawa Zewnętrzna (WZ)'
                    pdf_filename = f"Dostawa_WZ_{clean_ref}.pdf"
            else:
                doc_category = 'DOSTAWA_ZEWNETRZNA'
                doc_category_title = 'Dostawa Zewnętrzna (WZ)'
                pdf_filename = f"Dostawa_WZ_{clean_ref}.pdf"

            doc_items = []
            doc_summary_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for idx, it in enumerate(raw_items, start=1):
                pname_raw = it.get('productName') or 'Brak nazwy'
                pname = re.sub(r'\s+', ' ', str(pname_raw).strip())
                nr_pal = it.get('nr_palety') or '-'
                nr_partii = it.get('nr_partii') or '-'
                prod_date = it.get('data_produkcji') or '-'
                exp_date = it.get('data_przydatnosci') or '-'
                qty = cls.extract_item_qty(it)
                unit = ('szt' if it.get('packageForm') == 'packaging' else 'kg').strip().lower()
                source_spot = it.get('sourceSpot') or cat['source_value']
                target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
                
                status_info = WarehouseStatusResolver.resolve_item_status(it, d.get('status'))
                status_txt = status_info['status_label']
                accepted = status_info['is_accepted']

                item_obj = {
                    'lp': idx,
                    'product_name': pname,
                    'nr_palety': nr_pal,
                    'nr_partii': nr_partii,
                    'data_produkcji': prod_date,
                    'data_przydatnosci': exp_date,
                    'quantity': qty,
                    'unit': unit,
                    'source_spot': source_spot,
                    'target_spot': target_spot,
                    'status': status_txt,
                    'accepted': accepted
                }
                doc_items.append(item_obj)

                s_key = (pname.lower(), unit)
                if s_key not in doc_summary_map:
                    doc_summary_map[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                doc_summary_map[s_key]['count'] += 1
                doc_summary_map[s_key]['total_qty'] += qty

                if s_key not in all_products_summary:
                    all_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                all_products_summary[s_key]['count'] += 1
                all_products_summary[s_key]['total_qty'] += qty

                if doc_category == 'DOSTAWA_ZEWNETRZNA':
                    target_summary = deliveries_wz_products_summary
                elif doc_category == 'DOSTAWA_CENTRALA':
                    target_summary = deliveries_centrala_products_summary
                else:
                    target_summary = transfers_mm_products_summary

                if s_key not in target_summary:
                    target_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                target_summary[s_key]['count'] += 1
                target_summary[s_key]['total_qty'] += qty

                total_qty_by_unit[unit] = total_qty_by_unit.get(unit, 0.0) + qty
                total_pallets += 1

            doc_entry = {
                'id': d.get('id'),
                'order_ref': cat['ref'],
                'doc_type': doc_category,
                'category': doc_category,
                'doc_title': doc_category_title,
                'source': cat['source_value'],
                'destination': cat['dest_value'],
                'created_by': cat['created_by'],
                'created_str': cat['created_str'],
                'accepted_by': cat['accepted_by'],
                'accepted_str': cat['accepted_str'],
                'uwagi': d.get('uwagi') or '-',
                'items': doc_items,
                'items_count': len(doc_items),
                'summary': list(doc_summary_map.values()),
                'pdf_filename': pdf_filename,
                'raw_dostawa': d,
                'raw_items': raw_items,
                'raw_transfer': None
            }

            if doc_category == 'DOSTAWA_ZEWNETRZNA':
                deliveries_wz.append(doc_entry)
            elif doc_category == 'DOSTAWA_CENTRALA':
                deliveries_centrala.append(doc_entry)
            else:
                transfers_mm.append(doc_entry)

            all_documents.append(doc_entry)

        for tr in osip_transfers_rows:
            tr_id = tr.get('id')
            raw_t_items = osip_items_by_transfer.get(tr_id, [])
            code = tr.get('transfer_code') or f"TR-{tr_id}"
            clean_code = re.sub(r'[\s/\\:*?"<>|]+', '_', str(code)).strip('_')
            source = tr.get('source_warehouse') or 'Centrala'
            dest = tr.get('destination_warehouse') or 'OSIP'

            created_by = tr.get('created_by') or 'System'
            completed_by = tr.get('completed_by') or tr.get('approved_by') or '-'
            c_at = tr.get('created_at')
            created_str = c_at.strftime('%Y-%m-%d %H:%M') if hasattr(c_at, 'strftime') else str(c_at or '-')
            comp_at = tr.get('completed_at')
            completed_str = comp_at.strftime('%Y-%m-%d %H:%M') if hasattr(comp_at, 'strftime') else str(comp_at or '-')

            doc_items = []
            doc_summary_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for idx, it in enumerate(raw_t_items, start=1):
                pname = (it.get('product_name') or 'Brak nazwy').strip()
                nr_pal = it.get('pallet_sscc') or '-'
                nr_partii = it.get('batch_number') or '-'
                prod_date = str(it.get('production_date') or '-')
                exp_date = str(it.get('expiry_date') or '-')
                qty = float(it.get('loaded_weight') or it.get('requested_weight') or it.get('weight') or 0.0)
                unit = 'kg'
                it_status = str(it.get('status') or 'COMPLETED').upper()

                item_obj = {
                    'lp': idx,
                    'product_name': pname,
                    'nr_palety': nr_pal,
                    'nr_partii': nr_partii,
                    'data_produkcji': prod_date,
                    'data_przydatnosci': exp_date,
                    'quantity': qty,
                    'unit': unit,
                    'source_spot': source,
                    'target_spot': dest,
                    'status': it_status,
                    'accepted': it_status == 'RECEIVED'
                }
                doc_items.append(item_obj)

                s_key = (pname.lower(), unit)
                if s_key not in doc_summary_map:
                    doc_summary_map[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                doc_summary_map[s_key]['count'] += 1
                doc_summary_map[s_key]['total_qty'] += qty

                if s_key not in all_products_summary:
                    all_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                all_products_summary[s_key]['count'] += 1
                all_products_summary[s_key]['total_qty'] += qty

                if s_key not in transfers_mm_products_summary:
                    transfers_mm_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                transfers_mm_products_summary[s_key]['count'] += 1
                transfers_mm_products_summary[s_key]['total_qty'] += qty

                total_qty_by_unit[unit] = total_qty_by_unit.get(unit, 0.0) + qty
                total_pallets += 1

            pdf_filename = f"Przesuniecie_MM_{clean_code}.pdf"
            doc_entry = {
                'id': tr_id,
                'order_ref': code,
                'doc_type': 'TRANSFER_OSIP',
                'category': 'PRZESUNIECIE_MM',
                'doc_title': f'Przesunięcie MM ({source} ➔ {dest})',
                'source': source,
                'destination': dest,
                'created_by': created_by,
                'created_str': created_str,
                'accepted_by': completed_by,
                'accepted_str': completed_str,
                'uwagi': tr.get('notes') or '-',
                'items': doc_items,
                'items_count': len(doc_items),
                'summary': list(doc_summary_map.values()),
                'pdf_filename': pdf_filename,
                'raw_dostawa': None,
                'raw_transfer': tr,
                'raw_items': raw_t_items
            }
            transfers_mm.append(doc_entry)
            all_documents.append(doc_entry)

        has_activity = bool(all_documents)
        legacy_deliveries_products = list(deliveries_wz_products_summary.values()) + list(deliveries_centrala_products_summary.values())

        return {
            'date_str': date_str,
            'deliveries_wz': deliveries_wz,
            'deliveries_centrala': deliveries_centrala,
            'transfers_mm': transfers_mm,
            'all_documents': all_documents,
            'deliveries_wz_count': len(deliveries_wz),
            'deliveries_centrala_count': len(deliveries_centrala),
            'transfers_mm_count': len(transfers_mm),
            'all_documents_count': len(all_documents),
            'deliveries': deliveries_wz + deliveries_centrala,
            'transfers': transfers_mm,
            'deliveries_count': len(deliveries_wz) + len(deliveries_centrala),
            'transfers_count': len(transfers_mm),
            'total_pallets': total_pallets,
            'total_qty_by_unit': total_qty_by_unit,
            'deliveries_wz_products_summary': sorted(deliveries_wz_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'deliveries_centrala_products_summary': sorted(deliveries_centrala_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'transfers_mm_products_summary': sorted(transfers_mm_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'deliveries_products_summary': sorted(legacy_deliveries_products, key=lambda x: x['product_name'].lower()),
            'all_products_summary': sorted(all_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'has_activity': has_activity
        }
