"""
ScannerService — logika skanowania regałów i palet, dzielenia palet na worki
oraz przekazywania surowca na produkcję.

Schemat lokalizacji: R[regał:02d][rząd:02d][miejsce:02d]  np. R030102
                       ──────────────────────────────────────────
                       R  03   01   02
                       │   │    │    └── miejsce (slot) w rzędzie
                       │   │    └─────── rząd na regale
                       │   └──────────── nr regału
                       └──────────────── prefix
"""

from app.db import get_db_connection, get_table_name
from datetime import datetime
from dateutil.relativedelta import relativedelta
import re


class ScannerService:
    SCAN_TOKEN_PATTERN = re.compile(
        r'(R\d{6}|[A-Z]{3}\d{18,20}|SUR-?\d+|OPK-?\d+|DOD-?\d+|PAL-?\d+|MS01|MP01|MDM01|MOP01|MGW01|MGW02|OS\d{2}|OSIP|BB\d{2}|MZ\d{2}(?:-\d{2})?|BF_?MS01|BF_?MP01|BFOS|KO\d{2}|PSD01|PSD|RAMPA|MIX01|W_TRANZYCIE_OSIP)',
        re.IGNORECASE,
    )

    @staticmethod
    def _normalize_scanned_code(raw_code: str) -> str:
        if not raw_code:
            return ''
            
        raw_str = str(raw_code).strip()
        if ('{' in raw_str and '}' in raw_str) or ('"sscc"' in raw_str):
            try:
                import json
                j_match = re.search(r'\{[\s\S]*\}', raw_str)
                if j_match:
                    parsed = json.loads(j_match.group(0))
                    val = parsed.get('sscc') or parsed.get('nr_palety') or parsed.get('id')
                    if val:
                        raw_str = str(val)
                else:
                    sscc_m = re.search(r'"sscc"\s*:\s*"([^"]+)"', raw_str, re.IGNORECASE)
                    if sscc_m:
                        raw_str = sscc_m.group(1)
            except Exception:
                pass

        code = raw_str.strip().upper()
        if not code:
            return ''

        code = re.sub(r'[\r\n\t]+', ' ', code).strip()

        # GS1 SSCC często pojawia się jako AI(00) + 18 cyfr lub "00" + 18 cyfr.
        gs1_ai_match = re.search(r'\(00\)\s*(\d{18})', code)
        if gs1_ai_match:
            return gs1_ai_match.group(1)

        gs1_00_match = re.search(r'\b00(\d{18})\b', code)
        if gs1_00_match:
            return gs1_00_match.group(1)

        # Fallback dla etykiet zawierających sam 18-20 cyfrowy SSCC w dłuższym tekście.
        digits_18_20_match = re.search(r'\b\d{18,20}\b', code)
        if digits_18_20_match:
            return digits_18_20_match.group(0)

        # Zebra zwykle wysyła czysty tekst + Enter, ale część etykiet QR może mieć prefixy/URL.
        match = ScannerService.SCAN_TOKEN_PATTERN.search(code)
        if match:
            return match.group(1).upper()

        return code

    @staticmethod
    def _extract_prefixed_id(code: str) -> tuple[str | None, int | None]:
        # Obsługa zarówno SUR-123 jak i SUR123
        match = re.match(r'^(SUR|OPK|DOD|PAL)-?(\d+)$', str(code or '').strip().upper())
        if not match:
            return None, None
        prefix = match.group(1)
        digits = match.group(2)
        
        # Jeśli liczba ma więcej niż 10 cyfr, to prawdopodobnie SSCC/nr_palety, nie ID
        # W takim przypadku zwracamy None, żeby lookup szukał po nr_palety
        if len(digits) > 10:
            return None, None
            
        return prefix, int(digits)

    @staticmethod
    def _is_sscc_code(code: str) -> bool:
        normalized = str(code or '').strip().upper()
        # Obsługa SSCC 18-20 cyfr oraz z prefiksami literowymi
        return bool(re.match(r'^([A-Z]{3}\d{18,20}|\d{18,20}|00\d{18,20})$', normalized))

    @staticmethod
    def _get_active_production_qty(cur, surowiec_id: int, linia: str) -> tuple[float, str]:
        """Zwraca (pozostała_ilość_w_produkcji, zbiornik) dla danego surowca."""
        if not surowiec_id:
            return 0.0, ''
        try:
            table_ruch = get_table_name('magazyn_ruch', linia)
            cur.execute(
                f"SELECT r.id, ABS(r.ilosc) as pobrana, COALESCE(r.zbiornik, '') as zbiornik, "
                f"COALESCE((SELECT SUM(z.ilosc) FROM {table_ruch} z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as zwrocona, "
                f"COALESCE((SELECT SUM(k.ilosc) FROM {table_ruch} k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as korekta "
                f"FROM {table_ruch} r "
                f"WHERE r.surowiec_id = %s AND r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
                f"ORDER BY r.autor_data DESC, r.id DESC LIMIT 1",
                (surowiec_id,)
            )
            row = cur.fetchone()
            if row:
                pobrana = float(row.get('pobrana') or 0)
                zwrocona = float(row.get('zwrocona') or 0)
                korekta = float(row.get('korekta') or 0)
                rem = round(pobrana - zwrocona + korekta, 2)
                if rem > 0:
                    return rem, (row.get('zbiornik') or '').strip().upper()
        except Exception:
            pass
        return 0.0, ''

    @staticmethod
    def _lookup_inventory_row(
        cur,
        base_table: str,
        linia: str,
        *,
        qty_col: str,
        name_col: str = 'nazwa',
        location_code: str | None = None,
        item_id: int | None = None,
        pallet_no: str | None = None,
        partial_pallet_no: str | None = None,
    ) -> dict | None:
        table_name = get_table_name(base_table, linia)
        where = [f"COALESCE({qty_col}, 0) > 0"]
        params: list[object] = []

        if location_code is not None:
            where.append("UPPER(COALESCE(lokalizacja, '')) = %s")
            params.append(location_code)
        if item_id is not None:
            where.append("id = %s")
            params.append(item_id)
        if pallet_no is not None:
            where.append("UPPER(COALESCE(nr_palety, '')) = %s")
            params.append(str(pallet_no).upper())
        if partial_pallet_no is not None:
            where.append("UPPER(COALESCE(nr_palety, '')) LIKE %s")
            params.append('%' + str(partial_pallet_no).upper())

        sql = (
            f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, COALESCE(lokalizacja, '') AS lokalizacja, "
            f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
            f"data_produkcji, data_przydatnosci, '{linia}' AS linia "
            f"FROM {table_name} WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 1"
        )
        try:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            if row:
                return row
        except Exception:
            pass

        # Jeśli nie znaleziono z qty > 0, ale szukano po ID lub nr_palety — sprawdź czy paleta jest w produkcji
        if location_code is None and (item_id is not None or pallet_no is not None or partial_pallet_no is not None):
            where_unbound = []
            params_unbound: list[object] = []
            if item_id is not None:
                where_unbound.append("id = %s")
                params_unbound.append(item_id)
            if pallet_no is not None:
                where_unbound.append("UPPER(COALESCE(nr_palety, '')) = %s")
                params_unbound.append(str(pallet_no).upper())
            if partial_pallet_no is not None:
                where_unbound.append("UPPER(COALESCE(nr_palety, '')) LIKE %s")
                params_unbound.append('%' + str(partial_pallet_no).upper())

            if where_unbound:
                sql_unbound = (
                    f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, COALESCE(lokalizacja, '') AS lokalizacja, "
                    f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                    f"data_produkcji, data_przydatnosci, '{linia}' AS linia "
                    f"FROM {table_name} WHERE {' AND '.join(where_unbound)} ORDER BY id DESC LIMIT 1"
                )
                try:
                    cur.execute(sql_unbound, tuple(params_unbound))
                    p_row = cur.fetchone()
                    if p_row:
                        prod_qty, prod_tank = ScannerService._get_active_production_qty(cur, p_row['id'], linia)
                        if prod_qty > 0:
                            p_row['ilosc'] = prod_qty
                            if prod_tank:
                                p_row['lokalizacja'] = prod_tank
                            return p_row
                except Exception:
                    pass

        return None


    @staticmethod
    def _lookup_finished_goods(
        cur,
        linia: str,
        *,
        item_id: int | None = None,
        location_code: str | None = None,
        pallet_no: str | None = None,
        partial_pallet_no: str | None = None,
    ) -> dict | None:
        table_name = get_table_name('magazyn_palety', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        
        select_clause = (
            f"SELECT m.id, COALESCE(plan.produkt, m.produkt) AS nazwa, m.waga_netto AS ilosc, COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
            f"COALESCE(m.nr_palety, '') AS nr_palety, COALESCE(m.nr_partii, plan.nr_partii, '') AS nr_partii, "
            f"COALESCE(m.data_produkcji, plan.data_produkcji) AS data_produkcji, COALESCE(m.data_przydatnosci, plan.termin_przydatnosci) AS data_przydatnosci, "
            f"COALESCE(m.is_blocked, 0) AS is_blocked, '{linia}' AS linia "
            f"FROM {table_name} m "
            f"LEFT JOIN {table_plan} plan ON m.plan_id = plan.id "
        )

        if item_id is not None:
            try:
                cur.execute(
                    select_clause + f"WHERE m.id = %s AND COALESCE(m.waga_netto, 0) > 0 LIMIT 1",
                    (item_id,),
                )
                return cur.fetchone()
            except Exception:
                return None

        if pallet_no is not None:
            try:
                cur.execute(
                    select_clause + f"WHERE UPPER(COALESCE(m.nr_palety, '')) = %s AND COALESCE(m.waga_netto, 0) > 0 LIMIT 1",
                    (str(pallet_no).upper(),),
                )
                return cur.fetchone()
            except Exception:
                pass

        if partial_pallet_no is not None:
            try:
                cur.execute(
                    select_clause + f"WHERE UPPER(COALESCE(m.nr_palety, '')) LIKE %s AND COALESCE(m.waga_netto, 0) > 0 LIMIT 1",
                    ('%' + str(partial_pallet_no).upper(),),
                )
                return cur.fetchone()
            except Exception:
                pass

        normalized_location = str(location_code or '').strip().upper()
        if not normalized_location:
            return None

        try:
            cur.execute(
                select_clause + f"WHERE UPPER(COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE')) = %s AND COALESCE(m.waga_netto, 0) > 0 "
                "ORDER BY COALESCE(m.data_potwierdzenia, m.created_at) DESC, m.id DESC LIMIT 1",
                (normalized_location,),
            )
            return cur.fetchone()
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # LOOKUP — znajdź paletę po lokalizacji lub ID
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def lookup_by_location(location_code: str, linia: str = 'Agro', try_all_lines: bool = True) -> dict | None:
        """Zwraca dane pozycji magazynowej dla kodu lokalizacji lub ID.

        Obsługiwane prefiksy: SUR-, OPK-, DOD-, PAL-, SSCC AAA+18 cyfr oraz kody lokalizacji.
        Returns None jeśli nie znaleziono pozycji z ilością > 0.
        
        Args:
            location_code: Kod do wyszukania (QR, barcode, ID, lokalizacja)
            linia: Preferowana linia produkcyjna (domyślnie 'Agro')
            try_all_lines: Jeśli True i nie znaleziono w podanej linii, próbuje w innych liniach (domyślnie True)
        """
        is_sscc = ScannerService._is_sscc_code(location_code)
        results = []

        # Najpierw spróbuj w podanej linii
        res_list = ScannerService._lookup_by_location_internal(location_code, linia)
        if res_list:
            results.extend(res_list)
        
        # Jeśli nie znaleziono (lub zbieramy wszystkie dla SSCC) i try_all_lines=True, spróbuj w innych liniach
        if try_all_lines:
            other_lines = ['AGRO', 'PSD', 'Agro', 'Psd']
            normalized_linia = str(linia).upper()
            for other_linia in other_lines:
                if str(other_linia).upper() == normalized_linia:
                    continue  # Już sprawdziliśmy tę linię
                res_list = ScannerService._lookup_by_location_internal(location_code, other_linia)
                if res_list:
                    results.extend(res_list)
        
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
                
                # Priority:
                # 1. Not used up (active pallets over 0 kg)
                # 2. Has quantity > 0
                # 3. Not 'OCZEKUJĄCE' (physical location / station over pending receiving queue)
                # 4. Warehouse over production if both have stock > 0
                # 5. Quantity
                # 6. Newer ID
                has_qty = (qty > 0) and not is_used_up
                not_oczek = not is_oczek
                is_warehouse = (not is_prod) and not_oczek
                
                return (not is_used_up, has_qty, not_oczek, is_warehouse, qty, item_id)
                
            results.sort(key=sort_key, reverse=True)
            final_res = results[0]

        transfer_info = ScannerService._check_active_transfer_for_code(location_code)
        if not transfer_info and final_res:
            if final_res.get('nr_palety'):
                transfer_info = ScannerService._check_active_transfer_for_code(final_res.get('nr_palety'))
            if not transfer_info and final_res.get('id'):
                transfer_info = ScannerService._check_active_transfer_for_code(str(final_res.get('id')))


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
            return final_res
        elif transfer_info:
            it = transfer_info.get('item_details') or {}
            if not it and transfer_info.get('items'):
                for sub_it in transfer_info['items']:
                    if str(sub_it.get('nr_palety') or '').upper() == str(location_code).upper() or str(sub_it.get('pallet_id') or '') == str(location_code):
                        it = sub_it
                        break
                if not it and transfer_info['items']:
                    it = transfer_info['items'][0]

            p_name = it.get('productName') or it.get('product_name') or it.get('nazwa') or f"Transfer {transfer_info.get('transfer_code')}"
            pkg_form = str(it.get('packageForm') or '').lower()
            scanned_t = str(it.get('scannedType') or it.get('type') or '').lower()
            is_pkg = pkg_form == 'packaging' or scanned_t == 'opakowanie'
            is_dodatek = scanned_t == 'dodatek'
            inv_type = 'Opakowanie' if is_pkg else ('Dodatek' if is_dodatek else 'Surowiec')
            unit = 'szt.' if is_pkg else (it.get('unit') or 'kg')
            qty = float(it.get('unitsPerPallet') or it.get('netWeight') or it.get('loaded_qty') or it.get('requested_qty') or it.get('stan_magazynowy') or 0.0)
            nr_pal = it.get('nr_palety') or location_code
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

        # Sprawdź czy kod to wiadro z Maluchów (01-99, W01-W99)
        try:
            from app.services.bucket_maluch_service import BucketMaluchService
            from app.repositories.bucket_maluch_repository import BucketMaluchRepository
            norm_bucket = BucketMaluchService.normalize_bucket_code(location_code)
            if norm_bucket:
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

                    data_prod_str = bucket.get('data_produkcji').strftime('%Y-%m-%d %H:%M') if bucket.get('data_produkcji') else (bucket.get('created_at').strftime('%Y-%m-%d %H:%M') if bucket.get('created_at') else '')
                    data_przyd_str = bucket.get('data_przydatnosci').strftime('%Y-%m-%d %H:%M') if bucket.get('data_przydatnosci') else ''
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
    def _check_active_transfer_for_code(code: str):
        """Sprawdza czy kod/paleta należy do aktywnego transferu międzymagazynowego lub zlecenia przesunięcia."""
        if not code:
            return None
        code_clean = str(code).strip()
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT t.id, t.transfer_code, t.source_warehouse, t.destination_warehouse, t.status, t.created_by, t.created_at
                FROM osip_transfers t
                WHERE t.transfer_code = %s AND t.status IN ('PLANNED', 'IN_TRANSIT')
            """, (code_clean,))
            transfer = cursor.fetchone()

            if not transfer:
                cursor.execute("""
                    SELECT t.id, t.transfer_code, t.source_warehouse, t.destination_warehouse, t.status, t.created_by, t.created_at
                    FROM osip_transfer_items ti
                    JOIN osip_transfers t ON ti.transfer_id = t.id
                    WHERE (ti.nr_palety = %s OR (ti.pallet_id = %s AND %s != '0')) AND t.status IN ('PLANNED', 'IN_TRANSIT')
                    LIMIT 1
                """, (code_clean, code_clean if code_clean.isdigit() else 0, code_clean if code_clean.isdigit() else '0'))
                transfer = cursor.fetchone()

            if transfer:
                cursor.execute("""
                    SELECT id, pallet_id, nr_palety, product_name, requested_qty, loaded_qty, unit, status
                    FROM osip_transfer_items
                    WHERE transfer_id = %s
                """, (transfer['id'],))
                items = cursor.fetchall()
                transfer['items'] = items
                if transfer.get('created_at') and hasattr(transfer['created_at'], 'strftime'):
                    transfer['created_at'] = transfer['created_at'].strftime('%Y-%m-%d %H:%M')
                elif transfer.get('created_at'):
                    transfer['created_at'] = str(transfer['created_at'])
                return transfer

            # Sprawdź również magazyn_dostawy (oczekujące przesunięcia wewnętrzne i dostawy)
            import json
            cursor.execute("""
                SELECT id, supplier, lokalizacja_z, lokalizacja_do, status, created_at, items, linia
                FROM magazyn_dostawy
                WHERE status IN ('OCZEKUJE', 'OPEN')
                ORDER BY id DESC
            """)
            dostawy = cursor.fetchall()
            code_clean_upper = code_clean.upper()
            for d in dostawy:
                raw_items = d.get('items')
                if not raw_items:
                    continue
                try:
                    d_items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue
                if not isinstance(d_items, list):
                    continue

                for it in d_items:
                    if not isinstance(it, dict):
                        continue
                    if it.get('accepted') or it.get('rejected'):
                        continue
                    
                    it_nr = str(it.get('nr_palety') or it.get('sourcePalletNo') or '').strip().upper()
                    it_id = str(it.get('sourcePalletId') or it.get('id') or '')
                    
                    if (it_nr and it_nr == code_clean_upper) or (it_id and it_id == code_clean):
                        created_str = d['created_at'].strftime('%Y-%m-%d %H:%M') if hasattr(d.get('created_at'), 'strftime') else str(d.get('created_at') or '')
                        src_spot = it.get('sourceSpot') or d.get('lokalizacja_z') or 'MAGAZYN'
                        dst_spot = it.get('lokalizacja_przyjecia') or d.get('lokalizacja_do') or 'OCZEKUJĄCE'
                        return {
                            'id': d['id'],
                            'transfer_code': d.get('supplier') or f"Zlecenie #{d['id'][:8] if isinstance(d['id'], str) else d['id']}",
                            'source_warehouse': src_spot,
                            'destination_warehouse': dst_spot,
                            'status': 'OCZEKUJE',
                            'created_at': created_str,
                            'linia': d.get('linia', 'PSD'),
                            'is_magazyn_dostawy': True,
                            'item_details': it
                        }
            return None
        except Exception as e:
            print(f"Error checking active transfer for code {code}: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @staticmethod
    def _lookup_by_location_internal(location_code: str, linia: str) -> list[dict]:
        """Wewnętrzna funkcja wyszukiwania dla konkretnej linii produkcyjnej.
           Dla kodów SSCC lub lokalizacji zwraca LISTĘ wszystkich dopasowań.
        """
        location_code = ScannerService._normalize_scanned_code(location_code)
        if not location_code:
            return []

        is_sscc_flag = ScannerService._is_sscc_code(location_code)

        # Nowa obsługa dla półek regału półkowego R09 (wieloasortymentowość na półce)
        if not is_sscc_flag and location_code.startswith('R09'):
            conn = get_db_connection()
            try:
                cur = conn.cursor(dictionary=True)
                items = []
                inventory_sources_shelf = [
                    ('magazyn_surowce', 'stan_magazynowy', 'nazwa', 'Surowiec', 'SUR', True, True, True),
                    ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'Opakowanie', 'OPK', False, False, True),
                    ('magazyn_dodatki', 'stan_magazynowy', 'nazwa', 'Dodatek', 'DOD', False, False, True),
                    ('magazyn_palety', 'waga_netto', 'produkt', 'Wyrób Gotowy', 'PAL', False, False, True),
                ]
                for base_table, qty_col, name_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources_shelf:
                    table_name = get_table_name(base_table, linia)
                    try:
                        sql = (
                            f"SELECT id, {qty_col} AS ilosc, {name_col} AS nazwa, COALESCE(lokalizacja, '') AS lokalizacja, "
                            f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                            f"data_produkcji, data_przydatnosci "
                            f"FROM {table_name} WHERE UPPER(COALESCE(lokalizacja, '')) = %s AND COALESCE({qty_col}, 0) > 0 "
                            f"ORDER BY id ASC"
                        )
                        cur.execute(sql, (location_code,))
                        rows = cur.fetchall()
                        for row in rows:
                            items.append(_normalize_lookup_item(
                                row,
                                inventory_type=inv_type,
                                inventory_key=code_prefix,
                                code_prefix=code_prefix,
                                can_dispatch=can_dispatch,
                                can_split=can_split,
                                can_print_label=can_print,
                            ))
                    except Exception:
                        pass
                
                return [{
                    'is_station': True,
                    'is_shelf': True,
                    'station_code': location_code,
                    'id': None,
                    'nazwa': f"Półka {location_code} (Regał R09)",
                    'stan_magazynowy': len(items),
                    'lokalizacja': location_code,
                    'nr_palety': '',
                    'nr_partii': '',
                    'data_produkcji': '',
                    'data_przydatnosci': '',
                    'inventory_type': 'Półka Magazynowa (R09)',
                    'inventory_key': 'POLKA',
                    'inventory_code': location_code,
                    'can_dispatch': False,
                    'can_split': False,
                    'can_print_label': False,
                    'items': items,
                    'skladniki': items,
                    'unit': 'poz.'
                }]
            finally:
                conn.close()

        results = []
        normalized_for_lookup = str(location_code).upper()
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            inventory_sources = [
                ('magazyn_surowce', 'stan_magazynowy', 'nazwa', 'Surowiec', 'SUR', True, True, True),
                ('magazyn_palety', 'waga_netto', 'produkt', 'Wyrób Gotowy', 'PAL', False, False, True),
                ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'Opakowanie', 'OPK', False, False, True),
                ('magazyn_dodatki', 'stan_magazynowy', 'nazwa', 'Dodatek', 'DOD', False, False, True),
            ]
            
            for base_table, qty_col, name_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                table_name = get_table_name(base_table, linia)
                try:
                    if base_table == 'magazyn_palety':
                        plan_table = get_table_name('plan_produkcji', linia)
                        sql = (
                            f"SELECT m.id, m.{qty_col} AS ilosc, COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób Gotowy') AS nazwa, "
                            f"COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
                            f"COALESCE(m.nr_palety, '') AS nr_palety, "
                            f"COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, '') AS nr_partii, "
                            f"COALESCE(m.data_produkcji, plan.data_produkcji, m.data_planu, plan.data_planu) AS data_produkcji, "
                            f"COALESCE(m.data_przydatnosci, plan.termin_przydatnosci) AS data_przydatnosci "
                            f"FROM {table_name} m "
                            f"LEFT JOIN {plan_table} plan ON m.plan_id = plan.id "
                            f"WHERE UPPER(COALESCE(m.nr_palety, '')) = %s ORDER BY m.{qty_col} DESC, m.id DESC"
                        )
                    else:
                        sql = (
                            f"SELECT id, {qty_col} AS ilosc, {name_col} AS nazwa, COALESCE(NULLIF(TRIM(lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
                            f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                            f"data_produkcji, data_przydatnosci "
                            f"FROM {table_name} WHERE UPPER(COALESCE(nr_palety, '')) = %s ORDER BY {qty_col} DESC, id DESC"
                        )
                    cur.execute(sql, (normalized_for_lookup,))
                    rows = cur.fetchall()
                    for row in rows:
                        if base_table == 'magazyn_surowce' and float(row.get('ilosc') or 0) <= 0:
                            prod_qty, prod_tank = ScannerService._get_active_production_qty(cur, row['id'], linia)
                            if prod_qty > 0:
                                row['ilosc'] = prod_qty
                                if prod_tank:
                                    row['lokalizacja'] = prod_tank
                        results.append(_normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                            location_fallback='OCZEKUJĄCE',
                        ))
                except Exception:
                    pass
            
            # ========== PRIORYTET 2: Jeśli nie znaleziono w magazynach, szukaj w historii ruchów (produkcja) dla SSCC lub surowców ==========
            is_raw_pallet_check = ScannerService._is_sscc_code(location_code) or bool(re.match(r'^SUR-?\d+$', location_code, re.I))
            if not results and is_raw_pallet_check:
                try:
                    table_ruch = get_table_name('magazyn_ruch', linia)
                    sql = (
                        f"SELECT r.*, m.nazwa, m.nr_partii, m.data_produkcji, m.data_przydatnosci "
                        f"FROM {table_ruch} r "
                        f"LEFT JOIN {get_table_name('magazyn_surowce', linia)} m ON r.surowiec_id = m.id "
                        f"WHERE UPPER(COALESCE(r.nr_palety, '')) = %s "
                        f"ORDER BY r.created_at DESC, r.id DESC LIMIT 1"
                    )
                    cur.execute(sql, (normalized_for_lookup,))
                    row = cur.fetchone()
                    if row:
                        s_id = row.get('surowiec_id') or row.get('id')
                        prod_qty, prod_tank = ScannerService._get_active_production_qty(cur, s_id, linia)
                        actual_qty = prod_qty if prod_qty > 0 else abs(float(row.get('ilosc', 0) or 0))
                        actual_loc = prod_tank or (row.get('lokalizacja_do') or row.get('lokalizacja') or '').strip().upper()
                        results.append({
                            'id': s_id,
                            'nazwa': row.get('nazwa') or '',
                            'stan_magazynowy': actual_qty,
                            'lokalizacja': actual_loc,
                            'nr_palety': row.get('nr_palety') or '',
                            'nr_partii': row.get('nr_partii') or '',
                            'data_produkcji': row.get('data_produkcji').strftime('%Y-%m-%d') if row.get('data_produkcji') else '',
                            'data_przydatnosci': row.get('data_przydatnosci').strftime('%Y-%m-%d') if row.get('data_przydatnosci') else '',
                            'inventory_type': 'Surowiec (Produkcja)',
                            'inventory_key': 'SUR',
                            'inventory_code': f"SUR-{s_id}",
                            'can_dispatch': False,
                            'can_split': False,
                            'can_print_label': False,
                            'unit': 'kg',
                        })
                except Exception:
                    pass
        finally:
            conn.close()

        if results:
            return results

        # Nowa obsługa dla stacji zasypowych i maszyn (np. LP01) - zwraca listę
        if not is_sscc_flag and (location_code.startswith(('OS', 'BB', 'MZ', 'KO', 'PSD', 'MIX', 'BF_', 'LP')) or location_code == 'MASZYNA'):
            conn = get_db_connection()
            try:
                cur = conn.cursor(dictionary=True)
                items = []
                inventory_sources = [
                    ('magazyn_surowce', 'stan_magazynowy', 'Surowiec', 'SUR', True, True, True),
                    ('magazyn_opakowania', 'stan_magazynowy', 'Opakowanie', 'OPK', False, False, False),
                    ('magazyn_dodatki', 'stan_magazynowy', 'Dodatek', 'DOD', False, False, False),
                ]
                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    table_name = get_table_name(base_table, linia)
                    sql = (
                        f"SELECT id, {qty_col} AS ilosc, nazwa, COALESCE(lokalizacja, '') AS lokalizacja, "
                        f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                        f"data_produkcji, data_przydatnosci "
                        f"FROM {table_name} WHERE UPPER(COALESCE(lokalizacja, '')) = %s AND COALESCE({qty_col}, 0) > 0"
                    )
                    cur.execute(sql, (location_code,))
                    rows = cur.fetchall()
                    for row in rows:
                        items.append(_normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        ))
                
                # Dodatkowo sprawdź aktywne surowce na stacji z historii ruchów produkcyjnych
                try:
                    from app.repositories.agro_tanks_repository import AgroTanksRepository, _normalize_tank_code
                    norm_code = _normalize_tank_code(location_code)
                    prod_inventory = AgroTanksRepository.get_production_inventory(limit=1000, linia=linia)
                    existing_ids = {it['id'] for it in items}
                    for p_item in prod_inventory:
                        p_zbiornik = _normalize_tank_code(p_item.get('zbiornik'))
                        if (p_zbiornik == norm_code or str(p_item.get('lokalizacja')).upper() == location_code) and p_item.get('surowiec_id') not in existing_ids:
                            items.append({
                                'id': p_item['surowiec_id'],
                                'nazwa': p_item['nazwa'],
                                'stan_magazynowy': float(p_item.get('stan_systemowy') or 0),
                                'lokalizacja': location_code,
                                'nr_palety': p_item.get('nr_palety') or f"SUR-{p_item['surowiec_id']}",
                                'nr_partii': '',
                                'data_produkcji': '',
                                'data_przydatnosci': '',
                                'inventory_type': 'Surowiec (Produkcja)',
                                'inventory_key': 'SUR',
                                'inventory_code': f"SUR-{p_item['surowiec_id']}",
                                'can_dispatch': False,
                                'can_split': False,
                                'can_print_label': True,
                                'unit': 'kg',
                            })
                            existing_ids.add(p_item.get('surowiec_id'))
                except Exception:
                    pass

                # Zwracamy specjalny obiekt z listą (nawet pustą), aby frontend pokazał stan stacji
                return [{
                    'is_station': True,
                    'station_code': location_code,
                    'items': items
                }]

            finally:
                conn.close()



        prefixed_type, prefixed_id = ScannerService._extract_prefixed_id(location_code)
        is_sscc = ScannerService._is_sscc_code(location_code)
        is_partial_sscc = location_code.isdigit() and len(location_code) >= 5

        numeric_id = None
        if prefixed_id is not None:
            numeric_id = prefixed_id
        else:
            try:
                numeric_id = int(location_code)
            except ValueError:
                numeric_id = None

        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)

            inventory_sources = [
                ('magazyn_surowce', 'stan_magazynowy', 'Surowiec', 'SUR', True, True, True),
                ('magazyn_opakowania', 'stan_magazynowy', 'Opakowanie', 'OPK', False, False, False),
                ('magazyn_dodatki', 'stan_magazynowy', 'Dodatek', 'DOD', False, False, False),
            ]

            is_new_pallet_format = bool(re.match(r'^[A-Z]{3}\d{18}$', location_code))

            should_check_unconfirmed = (
                is_sscc
                or is_partial_sscc
                or prefixed_type == 'PAL'
                or (prefixed_type is None and numeric_id is not None)
                or is_new_pallet_format
            )
            if should_check_unconfirmed:
                table_prod = 'palety_workowanie' if str(linia).upper() == 'PSD' else 'palety_agro'
                table_plan = 'plan_produkcji' if str(linia).upper() == 'PSD' else 'plan_produkcji_agro'
                try:
                    numeric_lookup = prefixed_id if prefixed_type == 'PAL' else numeric_id
                    if numeric_lookup is not None and not is_sscc:
                        # Search by numeric ID or pallet number.
                        cur.execute(
                            f"SELECT p.id, p.nr_palety, p.waga, plan.produkt as nazwa, plan.data_produkcji, NULL as nr_partii, NULL as data_przydatnosci "
                            f"FROM {table_prod} p "
                            f"LEFT JOIN {table_plan} plan ON p.plan_id = plan.id "
                            f"WHERE (p.id = %s OR UPPER(COALESCE(p.nr_palety,'')) = %s) AND p.status = 'do_przyjecia'",
                            (numeric_lookup, location_code)
                        )
                    else:
                        # SSCC or barcode — search only by nr_palety.
                        if is_partial_sscc and not is_sscc:
                            cur.execute(
                                f"SELECT p.id, p.nr_palety, p.waga, plan.produkt as nazwa, plan.data_produkcji, NULL as nr_partii, NULL as data_przydatnosci "
                                f"FROM {table_prod} p "
                                f"LEFT JOIN {table_plan} plan ON p.plan_id = plan.id "
                                f"WHERE UPPER(COALESCE(p.nr_palety,'')) LIKE %s AND p.status = 'do_przyjecia'",
                                ('%' + location_code,)
                            )
                        else:
                            cur.execute(
                                f"SELECT p.id, p.nr_palety, p.waga, plan.produkt as nazwa, plan.data_produkcji, NULL as nr_partii, NULL as data_przydatnosci "
                                f"FROM {table_prod} p "
                                f"LEFT JOIN {table_plan} plan ON p.plan_id = plan.id "
                                f"WHERE UPPER(COALESCE(p.nr_palety,'')) = %s AND p.status = 'do_przyjecia'",
                                (location_code,)
                            )
                    unconf_row = cur.fetchone()
                    if unconf_row:
                        dp = unconf_row.get('data_produkcji')
                        dp_str = dp.strftime('%Y-%m-%d') if hasattr(dp, 'strftime') else (str(dp) if dp else '')
                        dz = unconf_row.get('data_przydatnosci')
                        dz_str = dz.strftime('%Y-%m-%d') if hasattr(dz, 'strftime') else (str(dz) if dz else '')
                        results.append({
                            'id': unconf_row['id'],
                            'nr_palety': unconf_row['nr_palety'],
                            'nazwa': unconf_row['nazwa'] or '',
                            'stan_magazynowy': float(unconf_row['waga'] or 0),
                            'lokalizacja': '',
                            'inventory_type': 'Wyrób Gotowy',
                            'is_unconfirmed_wg': True,
                            'data_produkcji': dp_str,
                            'nr_partii': unconf_row.get('nr_partii') or '',
                            'data_przydatnosci': dz_str
                        })
                except Exception:
                    pass

            if prefixed_type:
                prefixed_row = None
                if prefixed_type == 'PAL':
                    prefixed_row = ScannerService._lookup_finished_goods(cur, linia, item_id=prefixed_id)
                    if prefixed_row:
                        results.append(_normalize_lookup_item(
                            prefixed_row,
                            inventory_type='Wyrób Gotowy',
                            inventory_key='WYROB_GOTOWY',
                            code_prefix='PAL',
                            can_dispatch=False,
                            can_split=False,
                            can_print_label=False,
                            location_fallback='OCZEKUJĄCE',
                        ))

                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    if code_prefix != prefixed_type:
                        continue
                    prefixed_row = ScannerService._lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        item_id=prefixed_id,
                    )
                    if prefixed_row:
                        val = _normalize_lookup_item(
                            prefixed_row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        )
                        results.append(val)
                        if not is_sscc:
                            return results

            if is_sscc or is_partial_sscc or is_new_pallet_format:
                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    sscc_row = ScannerService._lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        pallet_no=location_code if (is_sscc or is_new_pallet_format) else None,
                        partial_pallet_no=location_code if is_partial_sscc and not is_sscc and not is_new_pallet_format else None,
                    )
                    if sscc_row:
                        val = _normalize_lookup_item(
                            sscc_row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        )
                        results.append(val)
                        if not is_sscc:
                            return results

                fg_row = ScannerService._lookup_finished_goods(
                    cur, 
                    linia, 
                    pallet_no=location_code if (is_sscc or is_new_pallet_format) else None,
                    partial_pallet_no=location_code if is_partial_sscc and not is_sscc and not is_new_pallet_format else None,
                )
                if fg_row:
                    val = _normalize_lookup_item(
                        fg_row,
                        inventory_type='Wyrób Gotowy',
                        inventory_key='WYROB_GOTOWY',
                        code_prefix='PAL',
                        can_dispatch=False,
                        can_split=False,
                        can_print_label=False,
                        location_fallback='OCZEKUJĄCE',
                    )
                    results.append(val)
                    if not is_sscc:
                        return results

            # 1) Lookup po lokalizacji w magazynach z kolumną lokalizacja.
            for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                row = ScannerService._lookup_inventory_row(
                    cur,
                    base_table,
                    linia,
                    qty_col=qty_col,
                    location_code=location_code,
                )
                if row:
                    val = _normalize_lookup_item(
                        row,
                        inventory_type=inv_type,
                        inventory_key=code_prefix,
                        code_prefix=code_prefix,
                        can_dispatch=can_dispatch,
                        can_split=can_split,
                        can_print_label=can_print,
                    )
                    results.append(val)
                    if not is_sscc:
                        return results

            # 2) Lookup lokalizacji MGW01/MGW02 dla wyrobów gotowych.
            row = ScannerService._lookup_finished_goods(cur, linia, location_code=location_code)
            if row:
                val = _normalize_lookup_item(
                    row,
                    inventory_type='Wyrób Gotowy',
                    inventory_key='WYROB_GOTOWY',
                    code_prefix='PAL',
                    can_dispatch=False,
                    can_split=False,
                    can_print_label=False,
                    location_fallback=location_code,
                )
                results.append(val)
                if not is_sscc:
                    return results

            # 2b) Lookup po numerze palety dla kodów innych niż prefiksy SUR/OPK/DOD/PAL.
            if prefixed_type is None:
                row = ScannerService._lookup_finished_goods(cur, linia, pallet_no=location_code)
                if row:
                    val = _normalize_lookup_item(
                        row,
                        inventory_type='Wyrób Gotowy',
                        inventory_key='WYROB_GOTOWY',
                        code_prefix='PAL',
                        can_dispatch=False,
                        can_split=False,
                        can_print_label=False,
                        location_fallback='OCZEKUJĄCE',
                    )
                    results.append(val)
                    if not is_sscc:
                        return results

            # 3) Lookup po ID liczbowym (kompatybilność wsteczna).
            if numeric_id is not None:
                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    row = ScannerService._lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        item_id=numeric_id,
                    )
                    if row:
                        val = _normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        )
                        results.append(val)
                        if not is_sscc:
                            return results

                row = ScannerService._lookup_finished_goods(cur, linia, item_id=numeric_id)
                if row:
                    val = _normalize_lookup_item(
                        row,
                        inventory_type='Wyrób Gotowy',
                        inventory_key='WYROB_GOTOWY',
                        code_prefix='PAL',
                        can_dispatch=False,
                        can_split=False,
                        can_print_label=False,
                        location_fallback='OCZEKUJĄCE',
                    )
            # 4) Sprawdzenie w magazyn_archiwum (dla zużytych/zarchiwizowanych palet)
            if not results and (is_sscc or is_partial_sscc or prefixed_type or numeric_id):
                try:
                    where_arch = ["UPPER(COALESCE(nr_palety, '')) = %s"]
                    params_arch = [normalized_for_lookup]
                    if is_partial_sscc:
                        where_arch.append("UPPER(COALESCE(nr_palety, '')) LIKE %s")
                        params_arch.append(f"%{normalized_for_lookup}%")
                    if numeric_id is not None:
                        where_arch.append("original_id = %s OR id = %s")
                        params_arch.extend([numeric_id, numeric_id])

                    sql_arch = f"""
                        SELECT id, original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, 
                               waga_ostatnia, lokalizacja_ostatnia, data_archiwizacji, user_login, komentarz
                        FROM magazyn_archiwum
                        WHERE {' OR '.join(where_arch)}
                        ORDER BY data_archiwizacji DESC LIMIT 1
                    """
                    cur.execute(sql_arch, tuple(params_arch))
                    arch_row = cur.fetchone()
                    if arch_row:
                        dt_arch = arch_row.get('data_archiwizacji')
                        dt_str = dt_arch.strftime('%Y-%m-%d %H:%M') if hasattr(dt_arch, 'strftime') else (str(dt_arch) if dt_arch else '')
                        last_loc = arch_row.get('lokalizacja_ostatnia') or 'PRODUKCJA'
                        arch_typ = arch_row.get('typ_palety') or 'Surowiec'
                        arch_code_prefix = 'PAL' if arch_typ == 'Wyrób Gotowy' else ('OPK' if arch_typ == 'Opakowanie' else ('DOD' if arch_typ == 'Dodatek' else 'SUR'))
                        
                        # Pobierz dodatkowe metadane (jeśli istnieją w inwentaryzacji)
                        dt_prod = ''
                        dt_exp = ''
                        opk_type = ''
                        if arch_row.get('nr_palety'):
                            try:
                                cur.execute("SELECT data_produkcji, data_przydatnosci, typ_opakowania FROM magazyn_inwentaryzacja_wpisy WHERE nr_palety = %s ORDER BY id DESC LIMIT 1", (arch_row['nr_palety'],))
                                meta_row = cur.fetchone()
                                if meta_row:
                                    dt_prod = str(meta_row.get('data_produkcji') or '')
                                    dt_exp = str(meta_row.get('data_przydatnosci') or '')
                                    opk_type = meta_row.get('typ_opakowania') or ''
                            except Exception:
                                pass

                        results.append({
                            'id': arch_row.get('original_id') or arch_row['id'],
                            'archive_id': arch_row['id'],
                            'nazwa': arch_row.get('nazwa') or 'Zużyty materiał',
                            'stan_magazynowy': 0.0,
                            'waga_ostatnia': float(arch_row.get('waga_ostatnia') or 0.0),
                            'lokalizacja': f"ZUZYTA ({last_loc})",
                            'lokalizacja_ostatnia': last_loc,
                            'linia': arch_row.get('linia') or linia,
                            'nr_palety': arch_row.get('nr_palety') or location_code,
                            'nr_partii': arch_row.get('nr_partii') or '',
                            'data_produkcji': dt_prod,
                            'data_przydatnosci': dt_exp,
                            'typ_opakowania': opk_type,
                            'inventory_type': arch_typ,
                            'inventory_key': arch_code_prefix,
                            'inventory_code': arch_row.get('nr_palety') or location_code,
                            'is_used_up': True,
                            'status_pl': 'Zużyta / Rozchodowana',
                            'used_up_info': f"Zużyto do 0 kg (waga ost.: {arch_row.get('waga_ostatnia', 0)} kg, {dt_str} na {last_loc}, {arch_row.get('user_login', '')})",
                            'can_dispatch': False,
                            'can_split': False,
                            'can_print_label': False,
                            'unit': 'kg',
                        })
                except Exception:
                    pass

            # 5) Jeśli podano 6 cyfr bez prefiksu R (np. 020701), sprawdź czy istnieje taki regał R020701
            if not results and re.match(r'^\d{6}$', location_code):
                rack_with_r = f"R{location_code}"
                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    row = ScannerService._lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        location_code=rack_with_r,
                    )
                    if row:
                        results.append(_normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        ))
                        return results

                row = ScannerService._lookup_finished_goods(cur, linia, location_code=rack_with_r)
                if row:
                    results.append(_normalize_lookup_item(
                        row,
                        inventory_type='Wyrób Gotowy',
                        inventory_key='WYROB_GOTOWY',
                        code_prefix='PAL',
                        can_dispatch=False,
                        can_split=False,
                        can_print_label=False,
                        location_fallback=rack_with_r,
                    ))
                    return results

            return results
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # DISPATCH — przekaż paletę (lub część) na produkcję
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def dispatch_to_production(
        surowiec_id: int,
        ilosc: float,
        worker_login: str,
        linia: str = 'Agro',
        plan_id: int | None = None,
        zbiornik: str | None = None,
        komentarz: str | None = None,
        pallet_type: str = 'Surowiec',
    ) -> tuple[bool, str, dict | None]:
        """Pobiera `ilosc` kg z palety (surowiec_id) na produkcję.

        Returns (success, message, extra_data)
        """
        if ilosc <= 0:
            return False, "Ilość musi być > 0", None

        if pallet_type == 'Opakowanie':
            table_surowce = get_table_name('magazyn_opakowania', linia)
        elif pallet_type == 'Dodatek':
            table_surowce = 'magazyn_dodatki'
        else:
            table_surowce = get_table_name('magazyn_surowce', linia)
            
        table_ruch    = get_table_name('magazyn_ruch',    linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, is_blocked, nr_partii, data_produkcji, data_przydatnosci FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            pallet = cur.fetchone()
            if not pallet:
                return False, f"Paleta #{surowiec_id} nie istnieje", None

            if pallet.get('is_blocked') or str(pallet.get('lokalizacja') or '').upper().startswith('OCZEK'):
                return False, f"BŁĄD: Paleta #{surowiec_id} ma status OCZEKUJĄCE na przyjęcie / jest ZABLOKOWANA. Nie można jej wydać na produkcję dopóki nie zostanie przyjęta na magazyn docelowy!", None

            from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id
            pallet_sscc = str(pallet.get('nr_palety') or '').strip()
            if not pallet_sscc or not is_valid_pallet_id(pallet_sscc):
                pallet_sscc = generate_pallet_id(linia, pallet_type)
                cur.execute(f"UPDATE {table_surowce} SET nr_palety = %s WHERE id = %s", (pallet_sscc, surowiec_id))
                pallet['nr_palety'] = pallet_sscc

            stan = float(pallet['stan_magazynowy'] or 0)
            if ilosc > stan:
                return False, f"Za duża ilość — dostępne: {stan:.1f} kg", None

            now = datetime.now()
            plan_id_val   = int(plan_id) if plan_id not in (None, '', 0, '0') else None
            
            # Normalize and validate zbiornik (REQUIRED for production dispatch)
            zbiornik_normalized = str(zbiornik or '').strip().upper() if zbiornik else None
            if not zbiornik_normalized:
                return False, "⚠️ Brak kodu zbiornika! Podaj zbiornik (np. BB02, MZ07) aby przenieść surowiec na produkcję.", None

            from app.utils.location_validator import is_deleted_station_code
            if is_deleted_station_code(zbiornik_normalized):
                return False, f"❌ Stacja/zbiornik {zbiornik_normalized} została wycofana/usunięta z systemu! Dozwolone: BB01-BB06, BB11-BB22, MZ07-MZ10, MZ23-MZ24, KO01-KO40.", None
            
            zbiornik_val = zbiornik_normalized
            lokalizacja_val = zbiornik_val  # lokalizacja = zbiornik (move to tank)

            # Walidacja zgodności surowca z przypisaniem zbiornika
            from app.services.tank_validation_service import TankValidationService
            is_valid_mat, err_mat = TankValidationService.validate_tank_material(
                kod_zbiornika=zbiornik_val,
                surowiec_nazwa=pallet.get('nazwa', ''),
                surowiec_id=surowiec_id
            )
            if not is_valid_mat:
                return False, err_mat, None

            is_partial = ilosc < stan
            lokalizacja_zrodlowa = (pallet.get('lokalizacja') or '').strip()

            if is_partial:
                # Częściowe pobranie: nie zmieniamy lokalizacji palety-matki
                cur.execute(
                    f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s",
                    (ilosc, surowiec_id)
                )
            else:
                # Cała paleta pobrana: ustawiamy stan na 0 i przenosimy do zbiornika
                cur.execute(
                    f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s, lokalizacja = %s WHERE id = %s",
                    (ilosc, lokalizacja_val, surowiec_id)
                )

            # Nowy stan
            cur.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
            stan_po = float(cur.fetchone()['stan_magazynowy'] or 0)

            # Ruch PRODUKCJA
            cur.execute(
                f"INSERT INTO {table_ruch} "
                "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                "autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, zbiornik) "
                "VALUES (%s,%s,'PRODUKCJA',%s,%s,%s,'POTWIERDZONE',%s,%s,%s,%s,%s,%s,%s)",
                (
                    surowiec_id, pallet['nazwa'], -ilosc, stan_po,
                    lokalizacja_zrodlowa,
                    worker_login, now, worker_login, now,
                    plan_id_val, komentarz, zbiornik_val
                )
            )

            # Zapisz także do palety_historia
            try:
                cur.execute(
                    "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) "
                    "VALUES (%s, %s, %s, %s, 'WYDANIE_PRODUKCJA', %s, %s, %s, %s)",
                    (
                        surowiec_id, pallet_sscc, linia, pallet_type.lower(),
                        lokalizacja_zrodlowa or 'Magazyn', zbiornik_val,
                        f"Wydanie do stacji {zbiornik_val} (ilość: {ilosc:.1f} kg)",
                        worker_login
                    )
                )
            except Exception as hist_err:
                print("Błąd zapisu palety_historia w dispatch_to_production:", hist_err)

            conn.commit()

            extra_data = {
                'is_partial': is_partial,
                'stan_po': stan_po,
                'ilosc_pobrana': ilosc,
                'zbiornik': zbiornik_val,
                'pallet_name': pallet['nazwa'],
                'nr_palety': pallet_sscc,
                'lokalizacja_zrodlowa': lokalizacja_zrodlowa,
                'id': surowiec_id
            }

            return True, f"Przekazano {ilosc:.1f} kg [{pallet['nazwa']}] na produkcję. Pozostało: {stan_po:.1f} kg", extra_data
        except Exception as e:
            conn.rollback()
            return False, f"Błąd: {e}", None
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MOVE — przenieś paletę między lokalizacjami
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def move_pallet(
        surowiec_id: int,
        nowa_lokalizacja: str,
        worker_login: str,
        linia: str = 'Agro',
    ) -> tuple[bool, str]:
        """Przenosi paletę na nową lokalizację i zapisuje historię w magazyn_ruch."""
        nowa_lokalizacja = str(nowa_lokalizacja or '').strip().upper()
        if not nowa_lokalizacja:
            return False, "Nie podano lokalizacji docelowej"

        # SPRAWDZENIE SŁOWNIKA LOKALIZACJI
        conn_dict = get_db_connection()
        try:
            cur_dict = conn_dict.cursor()
            cur_dict.execute("SELECT nazwa FROM magazyn_dozwolone_lokalizacje")
            dozwolone = [row[0].upper() for row in cur_dict.fetchall()]
        finally:
            conn_dict.close()

        is_valid = False
        for dozw_lok in dozwolone:
            if nowa_lokalizacja.startswith(dozw_lok):
                is_valid = True
                break
                
        if not is_valid:
            return False, f"Lokalizacja '{nowa_lokalizacja}' nie występuje w dozwolonym słowniku ustawień."

        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch    = get_table_name('magazyn_ruch',    linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, is_blocked FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            pallet = cur.fetchone()
            if not pallet:
                return False, f"Paleta #{surowiec_id} nie istnieje"

            # --- PRZYJĘCIE W LOCIE DLA PALETY W ZLECENIU PRZESUNIĘCIA LUB BLOKADA JAKOŚCIOWA ---
            nr_p = pallet.get('nr_palety')
            from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
            in_trf, trf_ref = DeliveryQueries.is_pallet_in_pending_transfer(pallet_id=surowiec_id, nr_palety=nr_p)
            is_in_transfer_acceptance = bool(in_trf)
            trf_order_ref = trf_ref or ''

            if pallet.get('is_blocked') and not is_in_transfer_acceptance:
                return False, f"BŁĄD: Paleta {nr_p or surowiec_id} jest zablokowana ręcznie (blokada magazynowa) i nie może być przesunięta."

            stara_lokalizacja = (pallet.get('lokalizacja') or '').strip().upper()
            if stara_lokalizacja == nowa_lokalizacja:
                return False, f"Paleta jest już na lokalizacji {nowa_lokalizacja}"

            # SPRAWDZENIE CZY REGAŁ NIE JEST ZAJĘTY PRZEZ INNĄ PALETĘ
            from app.utils.location_validator import check_rack_location_availability
            is_loc_available, error_msg = check_rack_location_availability(nowa_lokalizacja, current_nr_palety=pallet.get('nr_palety'))
            if not is_loc_available:
                return False, error_msg

            now = datetime.now()
            stan = float(pallet['stan_magazynowy'] or 0)

            # Zmień lokalizację i zdejmij ewentualną blokadę roboczą
            cur.execute(
                f"UPDATE {table_surowce} SET lokalizacja = %s, is_blocked = 0 WHERE id = %s",
                (nowa_lokalizacja, surowiec_id)
            )

            # Ruch PRZESUNIECIE
            cur.execute(
                f"INSERT INTO {table_ruch} "
                "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                "autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                "VALUES (%s,%s,'PRZESUNIECIE',%s,%s,%s,'POTWIERDZONE',%s,%s,%s,%s,%s)",
                (
                    surowiec_id, pallet['nazwa'], stan, stan,
                    nowa_lokalizacja,
                    worker_login, now, worker_login, now,
                    f"Przesunięcie skanerem: {stara_lokalizacja or 'Brak'} -> {nowa_lokalizacja}"
                )
            )
            conn.commit()

            # Powiadom serwis dostaw, aby ewentualnie automatycznie przyjąć paletę w zleceniu
            try:
                import logging
                logging.info(f"Triggering auto-accept for {pallet.get('nr_palety')} at {nowa_lokalizacja} by {worker_login}")
                from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
                from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
                from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
                from app.services.magazyn_dostawy.location_service import LocationService
                AcceptanceService.auto_accept_by_pallet_no(pallet.get('nr_palety'), nowa_lokalizacja, worker_login)
                
                from app.services.osip_transfer_service import OsipTransferService
                OsipTransferService.auto_receive_pallet_by_code(pallet.get('nr_palety') or str(surowiec_id), nowa_lokalizacja, worker_login)
            except Exception as ex:
                import logging
                logging.error(f"Błąd powiadamiania dostaw/transferów o przeniesieniu: {ex}")

            if is_in_transfer_acceptance:
                return True, f"✅ Przyjęto w zleceniu {trf_order_ref} na regał: {nowa_lokalizacja}"
            return True, f"Przeniesiono paletę [{pallet['nazwa']}] na lokalizację: {nowa_lokalizacja}"
        except Exception as e:
            conn.rollback()
            return False, f"Błąd: {e}"
        finally:
            conn.close()



    # ─────────────────────────────────────────────────────────────────────────
    # QR label data — dane do wydruku etykiety
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_label_data(identifier: str | int, linia: str = 'Agro', pallet_type: str | None = None) -> dict | None:
        """Zwraca słownik danych potrzebnych do wydruku etykiety ZPL.
        Zgodnie z wymogami systemu ZAWSZE szuka w pierwszej kolejności po unikalnym numerze SSCC (nr_palety).
        """
        if not identifier:
            return None

        clean_id_str = str(identifier).strip()
        sscc_code = ScannerService._normalize_scanned_code(clean_id_str)
        is_numeric = clean_id_str.isdigit() and len(clean_id_str) < 10
        numeric_id = int(clean_id_str) if is_numeric else None

        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            
            # 1. Sprawdź czy to Wiadro Maluchy
            try:
                cur.execute(
                    "SELECT id, kod_wiadra, nr_sscc, plan_id, linia, status, waga_calkowita, mieszalnik_kod, data_produkcji, data_przydatnosci, created_at "
                    "FROM wiaderka_maluchy WHERE UPPER(COALESCE(nr_sscc, '')) = %s OR id = %s LIMIT 1",
                    (sscc_code.upper(), numeric_id or 0)
                )
                b_row = cur.fetchone()
                if b_row:
                    from app.repositories.bucket_maluch_repository import BucketMaluchRepository
                    from app.services.bucket_maluch_service import BucketMaluchService
                    pozycje = BucketMaluchRepository.get_items_for_bucket(b_row['id'])
                    pozycje_txt = ", ".join([f"[{p['stacja_kod']}] {p['surowiec_nazwa']}" for p in pozycje]) or "Puste wiadro"
                    sscc = b_row.get('nr_sscc') or BucketMaluchService.generate_bucket_sscc(b_row['kod_wiadra'], b_row.get('plan_id', 0), b_row.get('created_at'))
                    data_prod = b_row.get('data_produkcji') or b_row.get('created_at') or datetime.now()
                    data_przyd = b_row.get('data_przydatnosci') or (data_prod + relativedelta(hours=24))

                    return {
                        'id': b_row['id'],
                        'nr_palety': sscc,
                        'nazwa': f"WIADRO {b_row['kod_wiadra']}: {pozycje_txt}",
                        'ilosc': float(len(pozycje)),
                        'jednostka': 'skł.',
                        'lokalizacja': 'Naważanie Maluchów',
                        'qr_data': sscc,
                        'partia': f"Zlecenie #{b_row.get('plan_id')}",
                        'data_produkcji': data_prod.strftime('%d.%m.%Y %H:%M'),
                        'data_przydatnosci': data_przyd.strftime('%d.%m.%Y %H:%M'),
                        'termin': data_przyd.strftime('%d.%m.%Y %H:%M'),
                        'data': data_prod.strftime('%d.%m.%Y %H:%M'),
                        'is_bucket': True,
                        'typ': 'WIADERKO'
                    }
            except Exception:
                pass

            # 2. Definicja konfiguracji wyszukiwania dla etykiet
            is_agro = (str(linia).upper() == 'AGRO') or (sscc_code and sscc_code.upper().startswith('AGR'))

            # Finished goods: łączymy m z plan_produkcji, aby mieć nazwę, partię i termin przydatności
            fg_configs = [
                ('magazyn_palety_agro', 'plan_produkcji_agro', 'AGRO') if is_agro else ('magazyn_palety', 'plan_produkcji', 'PSD'),
                ('magazyn_palety', 'plan_produkcji', 'PSD') if is_agro else ('magazyn_palety_agro', 'plan_produkcji_agro', 'AGRO'),
            ]

            prod_configs = [
                ('palety_agro', 'plan_produkcji_agro', 'AGRO') if is_agro else ('palety_workowanie', 'plan_produkcji', 'PSD'),
                ('palety_workowanie', 'plan_produkcji', 'PSD') if is_agro else ('palety_agro', 'plan_produkcji_agro', 'AGRO'),
            ]

            mat_configs = [
                ('magazyn_agro_surowce', 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', 'AGRO') if is_agro else ('magazyn_surowce', 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', 'PSD'),
                ('magazyn_agro_opakowania', 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', 'AGRO') if is_agro else ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', 'PSD'),
                ('magazyn_dodatki', 'stan_magazynowy', 'nazwa', 'DODATEK', 'DOD', linia),
                ('magazyn_surowce', 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', 'PSD') if is_agro else ('magazyn_agro_surowce', 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', 'AGRO'),
                ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', 'PSD') if is_agro else ('magazyn_agro_opakowania', 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', 'AGRO'),
            ]

            # KROK A: Szukaj BEZWZGLĘDNIE po SSCC / nr_palety (jeśli podano SSCC)
            if sscc_code:
                # 1. Wyroby gotowe w magazynie
                for mag_tbl, plan_tbl, item_line in fg_configs:
                    try:
                        sql = (
                            f"SELECT m.id, m.nr_palety, COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób Gotowy') AS nazwa, "
                            f"m.waga_netto AS stan_magazynowy, COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
                            f"COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, '') AS nr_partii, "
                            f"COALESCE(m.data_produkcji, plan.data_produkcji, m.data_planu, plan.data_planu) AS data_produkcji, "
                            f"COALESCE(m.data_przydatnosci, plan.termin_przydatnosci) AS data_przydatnosci "
                            f"FROM {mag_tbl} m "
                            f"LEFT JOIN {plan_tbl} plan ON m.plan_id = plan.id "
                            f"WHERE UPPER(COALESCE(m.nr_palety, '')) = %s ORDER BY m.waga_netto > 0 DESC, m.id DESC LIMIT 1"
                        )
                        cur.execute(sql, (sscc_code.upper(),))
                        row = cur.fetchone()
                        if row:
                            return ScannerService._build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
                    except Exception:
                        pass

                # 2. Palety produkcyjne niezatwierdzone
                for prod_tbl, plan_tbl, item_line in prod_configs:
                    try:
                        sql = (
                            f"SELECT p.id, p.nr_palety, COALESCE(plan.produkt, 'Wyrób Gotowy') AS nazwa, "
                            f"p.waga AS stan_magazynowy, 'PRODUKCJA' AS lokalizacja, "
                            f"COALESCE(plan.nr_partii, '') AS nr_partii, "
                            f"COALESCE(plan.data_produkcji, plan.data_planu, p.data_dodania) AS data_produkcji, "
                            f"plan.termin_przydatnosci AS data_przydatnosci "
                            f"FROM {prod_tbl} p "
                            f"LEFT JOIN {plan_tbl} plan ON p.plan_id = plan.id "
                            f"WHERE UPPER(COALESCE(p.nr_palety, '')) = %s ORDER BY p.waga > 0 DESC, p.id DESC LIMIT 1"
                        )
                        cur.execute(sql, (sscc_code.upper(),))
                        row = cur.fetchone()
                        if row:
                            return ScannerService._build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
                    except Exception:
                        pass

                # 3. Surowce, opakowania, dodatki
                for mat_tbl, qty_col, name_col, typ_name, prefix, item_line in mat_configs:
                    try:
                        sql = (
                            f"SELECT id, nr_palety, {name_col} AS nazwa, {qty_col} AS stan_magazynowy, "
                            f"COALESCE(NULLIF(TRIM(lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
                            f"COALESCE(nr_partii, '') AS nr_partii, "
                            f"data_produkcji, data_przydatnosci "
                            f"FROM {mat_tbl} WHERE UPPER(COALESCE(nr_palety, '')) = %s ORDER BY {qty_col} > 0 DESC, id DESC LIMIT 1"
                        )
                        cur.execute(sql, (sscc_code.upper(),))
                        row = cur.fetchone()
                        if row:
                            return ScannerService._build_label_dict(cur, row, item_line, prefix, typ_name, False)
                    except Exception:
                        pass

            # KROK B: Jeśli nie znaleziono po SSCC, sprawdź po ID liczbowym
            if numeric_id is not None:
                # 1. Wyroby gotowe
                for mag_tbl, plan_tbl, item_line in fg_configs:
                    try:
                        sql = (
                            f"SELECT m.id, m.nr_palety, COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób Gotowy') AS nazwa, "
                            f"m.waga_netto AS stan_magazynowy, COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
                            f"COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, '') AS nr_partii, "
                            f"COALESCE(m.data_produkcji, plan.data_produkcji, m.data_planu, plan.data_planu) AS data_produkcji, "
                            f"COALESCE(m.data_przydatnosci, plan.termin_przydatnosci) AS data_przydatnosci "
                            f"FROM {mag_tbl} m "
                            f"LEFT JOIN {plan_tbl} plan ON m.plan_id = plan.id "
                            f"WHERE m.id = %s LIMIT 1"
                        )
                        cur.execute(sql, (numeric_id,))
                        row = cur.fetchone()
                        if row:
                            return ScannerService._build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
                    except Exception:
                        pass

                # 2. Surowce, opakowania, dodatki
                for mat_tbl, qty_col, name_col, typ_name, prefix, item_line in mat_configs:
                    try:
                        sql = (
                            f"SELECT id, nr_palety, {name_col} AS nazwa, {qty_col} AS stan_magazynowy, "
                            f"COALESCE(NULLIF(TRIM(lokalizacja), ''), 'OCZEKUJĄCE') AS lokalizacja, "
                            f"COALESCE(nr_partii, '') AS nr_partii, "
                            f"data_produkcji, data_przydatnosci "
                            f"FROM {mat_tbl} WHERE id = %s ORDER BY {qty_col} > 0 DESC, id DESC LIMIT 1"
                        )
                        cur.execute(sql, (numeric_id,))
                        row = cur.fetchone()
                        if row:
                            return ScannerService._build_label_dict(cur, row, item_line, prefix, typ_name, False)
                    except Exception:
                        pass

                # 3. Palety produkcyjne
                for prod_tbl, plan_tbl, item_line in prod_configs:
                    try:
                        sql = (
                            f"SELECT p.id, p.nr_palety, COALESCE(plan.produkt, 'Wyrób Gotowy') AS nazwa, "
                            f"p.waga AS stan_magazynowy, 'PRODUKCJA' AS lokalizacja, "
                            f"COALESCE(plan.nr_partii, '') AS nr_partii, "
                            f"COALESCE(plan.data_produkcji, plan.data_planu, p.data_dodania) AS data_produkcji, "
                            f"plan.termin_przydatnosci AS data_przydatnosci "
                            f"FROM {prod_tbl} p "
                            f"LEFT JOIN {plan_tbl} plan ON p.plan_id = plan.id "
                            f"WHERE p.id = %s LIMIT 1"
                        )
                        cur.execute(sql, (numeric_id,))
                        row = cur.fetchone()
                        if row:
                            return ScannerService._build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
                    except Exception:
                        pass

            return None
        finally:
            conn.close()

    @staticmethod
    def _build_label_dict(cur, row: dict, linia: str, prefix: str, typ_name: str, is_fg: bool) -> dict:
        from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id
        nr_palety = (row.get('nr_palety') or '').strip()
        if not nr_palety or not is_valid_pallet_id(nr_palety):
            nr_palety = generate_pallet_id(linia, typ_name.lower())
            row['nr_palety'] = nr_palety
        qty = float(row.get('stan_magazynowy') or 0)
        
        # Jeśli surowiec jest na stacji produkcyjnej, sprawdź aktualny stan ze stacji
        if not is_fg and qty <= 0:
            prod_qty, prod_tank = ScannerService._get_active_production_qty(cur, row['id'], linia)
            if prod_qty > 0:
                qty = prod_qty
                if prod_tank:
                    row['lokalizacja'] = prod_tank

        lokalizacja = str(row.get('lokalizacja') or 'OCZEKUJĄCE').strip()
        if not lokalizacja:
            lokalizacja = 'OCZEKUJĄCE'

        dp = row.get('data_produkcji')
        dp_str = dp.strftime('%Y-%m-%d') if hasattr(dp, 'strftime') else (str(dp) if dp else datetime.now().strftime('%Y-%m-%d'))

        dz = row.get('data_przydatnosci')
        dz_str = ''
        if dz:
            if hasattr(dz, 'strftime'):
                dz_str = dz.strftime('%Y-%m-%d')
            else:
                dz_str = str(dz).strip()
                match = re.search(r'^(\d+)\s*mies', dz_str, re.IGNORECASE)
                if match and dp:
                    try:
                        months = int(match.group(1))
                        dp_date = dp if hasattr(dp, 'strftime') else datetime.strptime(str(dp_str)[:10], '%Y-%m-%d').date()
                        dz_str = (dp_date + relativedelta(months=months)).strftime('%Y-%m-%d')
                    except Exception:
                        pass
        if not dz_str:
            dz_str = '---'

        jednostka = 'szt.' if typ_name == 'OPAKOWANIE' else 'kg'

        return {
            'id': row['id'],
            'nr_palety': nr_palety,
            'sscc': nr_palety,
            'nazwa': row.get('nazwa') or 'Brak nazwy',
            'ilosc': qty,
            'lokalizacja': lokalizacja,
            'partia': row.get('nr_partii') or '---',
            'nr_partii': row.get('nr_partii') or '---',
            'data_produkcji': dp_str,
            'data': dp_str,
            'data_przydatnosci': dz_str,
            'termin': dz_str,
            'jednostka': jednostka,
            'typ': typ_name,
            'inventory_type': typ_name,
            'is_finished_product': is_fg,
            'qr_data': f"{nr_palety}|{lokalizacja}|{row.get('nazwa') or ''}"
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_pallet(row: dict) -> dict:
    return _normalize_lookup_item(
        row,
        inventory_type='Surowiec',
        inventory_key='SUR',
        code_prefix='SUR',
        can_dispatch=True,
        can_split=True,
        can_print_label=True,
    )


def _normalize_lookup_item(
    row: dict,
    *,
    inventory_type: str,
    inventory_key: str,
    code_prefix: str,
    can_dispatch: bool,
    can_split: bool,
    can_print_label: bool,
    location_fallback: str = 'OCZEKUJĄCE',
) -> dict:
    qty = float(row.get('ilosc', row.get('stan_magazynowy', 0)) or 0)
    is_used_up = qty <= 0
    raw_location = str(row.get('lokalizacja') or location_fallback or 'OCZEKUJĄCE').strip().upper()
    if not raw_location:
        raw_location = 'OCZEKUJĄCE'
    location = f"ZUZYTA (ostatnio: {raw_location})" if (is_used_up and raw_location and not raw_location.startswith('ZUZY')) else raw_location

    dp = row.get('data_produkcji')
    dp_str = dp.strftime('%Y-%m-%d') if hasattr(dp, 'strftime') else (str(dp) if dp else '')

    dz = row.get('data_przydatnosci')
    dz_str = ''
    if dz:
        if hasattr(dz, 'strftime'):
            dz_str = dz.strftime('%Y-%m-%d')
        else:
            dz_str = str(dz).strip()
            match = re.search(r'^(\d+)\s*mies', dz_str, re.IGNORECASE)
            if match and dp:
                try:
                    months = int(match.group(1))
                    dp_date = dp if hasattr(dp, 'strftime') else datetime.strptime(dp_str, '%Y-%m-%d').date()
                    dz_str = (dp_date + relativedelta(months=months)).strftime('%Y-%m-%d')
                except Exception:
                    pass

    from app.utils.pallet_label import is_packaging_item
    is_pkg = (inventory_type == 'Opakowanie') or is_packaging_item(
        row.get('nazwa'),
        unit=row.get('jednostka') or row.get('unit'),
        typ=row.get('typ') or row.get('typ_opakowania'),
        pallet_nr=row.get('nr_palety'),
    )
    unit_str = 'szt.' if is_pkg else (row.get('jednostka') or row.get('unit') or 'kg')

    return {
        'id': row['id'],
        'nazwa': row.get('nazwa') or '',
        'stan_magazynowy': qty,
        'lokalizacja': location,
        'nr_palety': row.get('nr_palety') or f"{code_prefix}-{row['id']}",
        'nr_partii': row.get('nr_partii', ''),
        'data_produkcji': dp_str,
        'data_przydatnosci': dz_str,
        'inventory_type': inventory_type,
        'inventory_key': inventory_key,
        'inventory_code': f"{code_prefix}-{row['id']}",
        'is_used_up': is_used_up,
        'status_pl': 'Zużyta / Rozchodowana' if is_used_up else inventory_type,
        'used_up_info': f"Pozycja posiada stan 0 {unit_str} (ostatnia znana lokalizacja: {raw_location})" if is_used_up else '',
        'can_dispatch': bool(can_dispatch) and not is_used_up,
        'can_split': bool(can_split) and not is_used_up,
        'can_print_label': bool(can_print_label),
        'unit': unit_str,
        'jednostka': unit_str,
        'is_pkg': is_pkg,
    }
