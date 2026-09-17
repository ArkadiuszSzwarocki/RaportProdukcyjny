"""Coordinator for resolving scanned codes and ranking match results."""
from __future__ import annotations

from app.services.scanner.scanner_code_normalizer import ScannerCodeNormalizer
from app.services.scanner.scanner_lookup_service import ScannerLookupService
from app.services.scanner.scanner_location_query_service import ScannerLocationQueryService


class ScannerResolutionService:
    """Coordinates lookup across lines, rank results, and enrich with transfer/bucket metadata."""

    @staticmethod
    def _check_bucket(location_code: str, linia: str):
        try:
            from app.services.bucket_maluch_service import BucketMaluchService
            from app.repositories.bucket_maluch_repository import BucketMaluchRepository
            norm_bucket = BucketMaluchService.normalize_bucket_code(location_code)
            if not norm_bucket:
                return None
            bucket = BucketMaluchRepository.find_active_or_completed_by_code(norm_bucket, linia)
            if not bucket:
                alt_linia = 'AGRO' if str(linia).upper() == 'PSD' else 'PSD'
                bucket = BucketMaluchRepository.find_active_or_completed_by_code(norm_bucket, alt_linia)
            if not bucket:
                bucket = BucketMaluchRepository.find_latest_by_code(norm_bucket)

            if bucket:
                pozycje = bucket.get('pozycje') or []
                pozycje_txt = ", ".join([f"[{p['stacja_kod']}] {p['surowiec_nazwa']}" for p in pozycje]) or "Brak pozycji"
                status_pl = {
                    'w_trakcie_nawazania': 'W trakcie naważania',
                    'skompletowane': 'Skompletowane (Gotowe do wsypania)',
                    'wrzucone_do_mieszalnika': f"Wsypane do mieszalnika ({bucket.get('mieszalnik_kod') or 'MI01'})"
                }.get(bucket.get('status'), bucket.get('status'))

                dp = bucket.get('data_produkcji') or bucket.get('created_at')
                data_prod_str = dp.strftime('%Y-%m-%d %H:%M') if (dp and hasattr(dp, 'strftime')) else ''
                dz = bucket.get('data_przydatnosci')
                data_przyd_str = dz.strftime('%Y-%m-%d %H:%M') if (dz and hasattr(dz, 'strftime')) else ''
                sscc = bucket.get('nr_sscc') or BucketMaluchService.generate_bucket_sscc(norm_bucket, bucket.get('plan_id', 0), bucket.get('created_at'))

                return {
                    'id': bucket['id'],
                    'nazwa': f"Wiadro {norm_bucket} ({pozycje_txt})",
                    'typ': 'Wiaderko',
                    'inventory_type': 'Wiaderko',
                    'is_bucket': True,
                    'kod_wiadra': norm_bucket,
                    'status': bucket.get('status'),
                    'status_pl': status_pl,
                    'stan_magazynowy': float(len(pozycje)),
                    'jednostka': 'skł.',
                    'lokalizacja': 'Naważanie Maluchów' if bucket.get('status') != 'wrzucone_do_mieszalnika' else (bucket.get('mieszalnik_kod') or 'MI01'),
                    'nr_palety': sscc,
                    'sscc': sscc,
                    'plan_id': bucket.get('plan_id'),
                    'linia': bucket.get('linia'),
                    'nr_partii': f"Zlecenie #{bucket.get('plan_id')}",
                    'data_produkcji': data_prod_str,
                    'data_przydatnosci': data_przyd_str,
                    'pozycje': pozycje
                }
        except Exception:
            pass
        return None

    @staticmethod
    def lookup_by_location(location_code: str, linia: str = 'Agro', try_all_lines: bool = True) -> dict | None:
        normalized_scan_code = ScannerCodeNormalizer.normalize_scanned_code(location_code) or str(location_code or '').strip()
        results = []
        res_list = ScannerLocationQueryService.lookup_by_location_internal(location_code, linia)
        if res_list:
            results.extend(res_list)
        
        if try_all_lines:
            other_lines = ['AGRO', 'PSD', 'Agro', 'Psd']
            normalized_linia = str(linia).upper()
            for other_linia in other_lines:
                if str(other_linia).upper() == normalized_linia:
                    continue
                res_sub = ScannerLocationQueryService.lookup_by_location_internal(location_code, other_linia)
                if res_sub:
                    results.extend(res_sub)
        
        final_res = None
        if results:
            from app.utils.location_validator import is_production_tank_code
            
            def sort_key(item):
                loc = str(item.get('lokalizacja') or '').upper()
                is_oczek = 'OCZEK' in loc
                is_prod = is_production_tank_code(loc)
                qty = float(item.get('stan_magazynowy') or item.get('ilosc') or 0)
                item_id = int(item.get('id') or 0)
                is_used_up = bool(item.get('is_used_up', False))
                
                has_qty = (qty > 0) and not is_used_up
                not_oczek = not is_oczek
                is_warehouse = (not is_prod) and not_oczek
                return (not is_used_up, has_qty, not_oczek, is_warehouse, qty, item_id)
                
            results.sort(key=sort_key, reverse=True)
            final_res = results[0]

        transfer_info = ScannerLookupService.check_active_transfer_for_code(normalized_scan_code)
        if not transfer_info and final_res:
            if final_res.get('nr_palety'):
                transfer_info = ScannerLookupService.check_active_transfer_for_code(final_res.get('nr_palety'))
            if not transfer_info and final_res.get('id'):
                transfer_info = ScannerLookupService.check_active_transfer_for_code(str(final_res.get('id')))

        if final_res:
            if transfer_info:
                final_res['is_transfer'] = True
                final_res['transfer'] = transfer_info
                final_res['can_dispatch'] = False
                final_res['status_pl'] = 'Oczekuje na przyjęcie'
                db_loc = str(final_res.get('lokalizacja') or '').strip()
                if db_loc == 'W_TRANZYCIE_OSIP':
                    code_tr = transfer_info.get('transfer_code', '')
                    final_res['lokalizacja'] = f"W TRANZYCIE ({code_tr})"
                    final_res['status_pl'] = 'W tranzycie'
                elif transfer_info.get('is_magazyn_dostawy'):
                    src = transfer_info.get('source_warehouse', '')
                    dst = transfer_info.get('destination_warehouse', '')
                    final_res['source_location'] = src
                    final_res['destination_location'] = dst
                    final_res['lokalizacja'] = 'OCZEKUJĄCE'
                    final_res['status_info'] = f"Przesunięcie: {src} ➔ {dst or 'PRZYJĘCIE'}"

                it_details = transfer_info.get('item_details') or {}
                trf_qty = float(
                    it_details.get('unitsPerPallet')
                    or it_details.get('netWeight')
                    or it_details.get('quantity')
                    or it_details.get('ilosc')
                    or it_details.get('stan_magazynowy')
                    or it_details.get('loaded_qty')
                    or 0.0
                )
                if trf_qty > 0 and (final_res.get('is_used_up') or float(final_res.get('stan_magazynowy') or 0) <= 0):
                    final_res['stan_magazynowy'] = trf_qty
                    final_res['is_used_up'] = False
                if it_details.get('nr_partii'):
                    final_res['nr_partii'] = it_details.get('nr_partii')
                if it_details.get('data_produkcji'):
                    final_res['data_produkcji'] = it_details.get('data_produkcji')
                if it_details.get('data_przydatnosci'):
                    final_res['data_przydatnosci'] = it_details.get('data_przydatnosci')
            return final_res

        elif transfer_info:
            it = transfer_info.get('item_details') or {}
            if not it and transfer_info.get('items'):
                for sub_it in transfer_info['items']:
                    sub_it_nr_raw = str(sub_it.get('nr_palety') or '').strip()
                    sub_it_nr = (ScannerCodeNormalizer.normalize_scanned_code(sub_it_nr_raw) or sub_it_nr_raw).upper()
                    scan_code_upper = str(normalized_scan_code).upper()
                    if sub_it_nr == scan_code_upper or str(sub_it.get('pallet_id') or '') == str(normalized_scan_code):
                        it = sub_it
                        break
                if not it and transfer_info['items']:
                    it = transfer_info['items'][0]

            p_name = it.get('productName') or it.get('product_name') or it.get('nazwa') or f"Transfer {transfer_info.get('transfer_code')}"
            pkg_form = str(it.get('packageForm') or '').lower()
            scanned_t = str(it.get('scannedType') or it.get('type') or '').lower()
            unit_val = str(it.get('unit') or '').lower()
            is_pkg = pkg_form in ('packaging', 'tasma', 'taśma', 'karton') or scanned_t == 'opakowanie' or unit_val == 'szt'
            is_dodatek = scanned_t == 'dodatek'
            inv_type = 'Opakowanie' if is_pkg else ('Dodatek' if is_dodatek else 'Surowiec')
            unit = 'szt.' if is_pkg else (it.get('unit') or 'kg')
            qty = float(it.get('unitsPerPallet') or it.get('netWeight') or it.get('loaded_qty') or it.get('requested_qty') or it.get('stan_magazynowy') or 0.0)
            nr_pal = it.get('nr_palety') or normalized_scan_code
            src = transfer_info.get('source_warehouse', '')
            dst = transfer_info.get('destination_warehouse', '')

            return {
                "id": it.get('id') or it.get('sourcePalletId') or transfer_info.get('id'),
                "item_id": it.get('id'),
                "dostawa_id": transfer_info.get('id'),
                "is_transfer": True,
                "transfer": transfer_info,
                "nazwa": p_name,
                "stan_magazynowy": qty,
                "unit": unit,
                "inventory_type": inv_type,
                "typ": inv_type,
                "nr_palety": nr_pal,
                "sscc": nr_pal,
                "nr_partii": it.get('nr_partii', '') or '—',
                "data_produkcji": it.get('data_produkcji', '') or '—',
                "data_przydatnosci": it.get('data_przydatnosci', '') or '—',
                "lokalizacja": "OCZEKUJĄCE",
                "source_location": src,
                "destination_location": dst,
                "is_used_up": False,
                "can_dispatch": False,
                "status_pl": "Oczekuje na przyjęcie",
                "status_info": f"Przesunięcie: {src} ➔ {dst or 'PRZYJĘCIE'}" if transfer_info.get('is_magazyn_dostawy') else f"Transfer {transfer_info.get('transfer_code')}: {src} ➔ {dst}"
            }

        bucket_res = ScannerResolutionService._check_bucket(location_code, linia)
        if bucket_res:
            return bucket_res

        return None
