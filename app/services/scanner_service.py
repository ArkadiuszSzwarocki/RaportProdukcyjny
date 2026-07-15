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
        r'(R\d{6}|[A-Z]{3}\d{18,20}|SUR-?\d+|OPK-?\d+|DOD-?\d+|PAL-?\d+|MS01|MP01|MDM01|MOP01|MGW01|MGW02|OS\d{2}|OSIP|BB\d{2}|MZ\d{2}(?:-\d{2})?|BF_MS01|BF_MP01|KO\d{2}|PSD01|PSD|RAMPA|MIX01|W_TRANZYCIE_OSIP)',
        re.IGNORECASE,
    )

    @staticmethod
    def _normalize_scanned_code(raw_code: str) -> str:
        code = str(raw_code or '').strip().upper()
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
            f"data_produkcji, data_przydatnosci "
            f"FROM {table_name} WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 1"
        )
        try:
            cur.execute(sql, tuple(params))
            return cur.fetchone()
        except Exception:
            if item_id is None:
                return None

            # Część tabel nie ma kolumny lokalizacja — fallback tylko dla lookupu po ID.
            fallback_sql = (
                f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, '' AS lokalizacja, "
                f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                f"data_produkcji, data_przydatnosci "
                f"FROM {table_name} WHERE COALESCE({qty_col}, 0) > 0 AND id = %s LIMIT 1"
            )
            try:
                cur.execute(fallback_sql, (item_id,))
                return cur.fetchone()
            except Exception:
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
            f"SELECT m.id, COALESCE(plan.produkt, m.produkt) AS nazwa, m.waga_netto AS ilosc, COALESCE(m.lokalizacja, 'MGW01') AS lokalizacja, "
            f"COALESCE(m.nr_palety, '') AS nr_palety, COALESCE(m.nr_partii, plan.nr_partii, '') AS nr_partii, "
            f"COALESCE(m.data_produkcji, plan.data_produkcji) AS data_produkcji, COALESCE(m.data_przydatnosci, plan.termin_przydatnosci) AS data_przydatnosci "
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
        if normalized_location not in {'MGW01', 'MGW02'}:
            return None

        try:
            cur.execute(
                select_clause + f"WHERE UPPER(COALESCE(m.lokalizacja, 'MGW01')) = %s AND COALESCE(m.waga_netto, 0) > 0 "
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
            if not is_sscc:
                return res_list[0]
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
                    if not is_sscc:
                        return res_list[0]
                    results.extend(res_list)
        
        if results:
            from app.utils.location_validator import is_production_tank_code
            
            def sort_key(item):
                loc = str(item.get('lokalizacja') or '').upper()
                is_prod = is_production_tank_code(loc)
                is_warehouse = not is_prod
                qty = float(item.get('stan_magazynowy', 0))
                # Chcemy: magazyn (True) wyżej niż produkcja (False), potem większa ilość
                return (is_warehouse, qty)
                
            # Dla SSCC zwracamy główną paletę z magazynu, unikając wskazywania częściowego worka na stacji
            results.sort(key=sort_key, reverse=True)
            return results[0]
            
        return None

    @staticmethod
    def _lookup_by_location_internal(location_code: str, linia: str) -> list[dict]:
        """Wewnętrzna funkcja wyszukiwania dla konkretnej linii produkcyjnej.
           Dla kodów SSCC lub lokalizacji zwraca LISTĘ wszystkich dopasowań.
        """
        location_code = ScannerService._normalize_scanned_code(location_code)
        if not location_code:
            return []

        results = []
        normalized_for_lookup = str(location_code).upper()
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            inventory_sources = [
                ('magazyn_surowce', 'stan_magazynowy', 'Surowiec', 'SUR', True, True, True),
                ('magazyn_opakowania', 'stan_magazynowy', 'Opakowanie', 'OPK', False, False, False),
                ('magazyn_dodatki', 'stan_magazynowy', 'Dodatek', 'DOD', False, False, False),
            ]
            
            for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                table_name = get_table_name(base_table, linia)
                try:
                    sql = (
                        f"SELECT id, {qty_col} AS ilosc, nazwa, COALESCE(lokalizacja, '') AS lokalizacja, "
                        f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                        f"data_produkcji, data_przydatnosci "
                        f"FROM {table_name} WHERE UPPER(COALESCE(nr_palety, '')) = %s ORDER BY {qty_col} DESC, id DESC"
                    )
                    cur.execute(sql, (normalized_for_lookup,))
                    rows = cur.fetchall()
                    for row in rows:
                        results.append(_normalize_lookup_item(
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
            
            # ========== PRIORYTET 2: Jeśli nie znaleziono w magazynach, szukaj w historii ruchów (produkcja) ==========
            if not results:
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
                        results.append({
                            'id': row.get('surowiec_id') or row.get('id'),
                            'nazwa': row.get('nazwa') or '',
                            'stan_magazynowy': float(row.get('ilosc', 0) or 0),
                            'lokalizacja': (row.get('lokalizacja_do') or row.get('lokalizacja') or '').strip().upper(),
                            'nr_palety': row.get('nr_palety') or '',
                            'nr_partii': row.get('nr_partii') or '',
                            'data_produkcji': row.get('data_produkcji').strftime('%Y-%m-%d') if row.get('data_produkcji') else '',
                            'data_przydatnosci': row.get('data_przydatnosci').strftime('%Y-%m-%d') if row.get('data_przydatnosci') else '',
                            'inventory_type': 'Surowiec (Produkcja)',
                            'inventory_key': 'SUR',
                            'inventory_code': f"SUR-{row.get('surowiec_id', row.get('id'))}",
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

        is_sscc_flag = ScannerService._is_sscc_code(location_code)

        # Nowa obsługa dla stacji zasypowych - zwraca listę
        if not is_sscc_flag and location_code.startswith(('OS', 'BB', 'MZ', 'KO', 'PSD', 'MIX', 'BF_')):
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
                        results.append({
                            'id': unconf_row['id'],
                            'nr_palety': unconf_row['nr_palety'],
                            'nazwa': unconf_row['nazwa'] or '',
                            'stan_magazynowy': float(unconf_row['waga'] or 0),
                            'lokalizacja': '',
                            'inventory_type': 'Wyrób Gotowy',
                            'is_unconfirmed_wg': True,
                            'data_produkcji': unconf_row['data_produkcji'],
                            'nr_partii': unconf_row['nr_partii'],
                            'data_przydatnosci': unconf_row.get('data_przydatnosci')
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
                            location_fallback='MGW01',
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
                        location_fallback='MGW01',
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
                        location_fallback='MGW01',
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
                        location_fallback='MGW01',
                    )
                    results.append(val)
                    if not is_sscc:
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
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja, is_blocked FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            pallet = cur.fetchone()
            if not pallet:
                return False, f"Paleta #{surowiec_id} nie istnieje", None

            if pallet.get('is_blocked'):
                return False, f"BŁĄD: Paleta #{surowiec_id} jest ZABLOKOWANA i nie może zostać wydana na produkcję!", None

            stan = float(pallet['stan_magazynowy'] or 0)
            if ilosc > stan:
                return False, f"Za duża ilość — dostępne: {stan:.1f} kg", None

            now = datetime.now()
            plan_id_val   = int(plan_id) if plan_id not in (None, '', 0, '0') else None
            
            # Normalize and validate zbiornik (REQUIRED for production dispatch)
            zbiornik_normalized = str(zbiornik or '').strip().upper() if zbiornik else None
            if not zbiornik_normalized:
                return False, "⚠️ Brak kodu zbiornika! Podaj zbiornik (np. BB02, MZ07) aby przenieść surowiec na produkcję.", None
            
            zbiornik_val = zbiornik_normalized
            lokalizacja_val = zbiornik_val  # lokalizacja = zbiornik (move to tank)

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
            conn.commit()

            extra_data = {
                'is_partial': is_partial,
                'stan_po': stan_po,
                'ilosc_pobrana': ilosc,
                'zbiornik': zbiornik_val,
                'pallet_name': pallet['nazwa'],
                'nr_palety': pallet.get('nr_palety') or f"{pallet_type[:3].upper()}-{surowiec_id}",
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

            if pallet.get('is_blocked'):
                return False, f"BŁĄD: Paleta #{surowiec_id} jest ZABLOKOWANA i nie może być przenoszona!"

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

            # Zmień lokalizację
            cur.execute(
                f"UPDATE {table_surowce} SET lokalizacja = %s WHERE id = %s",
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
            except Exception as ex:
                import logging
                logging.error(f"Błąd powiadamiania dostaw o przeniesieniu: {ex}")

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
    def get_label_data(surowiec_id: int, linia: str = 'Agro') -> dict | None:
        """Zwraca słownik danych potrzebnych do wydruku etykiety ZPL."""
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            tables = [
                (get_table_name('magazyn_surowce', linia), 'SUR'),
                (get_table_name('magazyn_opakowania', linia), 'OPK'),
                ('magazyn_dodatki', 'DOD')
            ]
            for table_name, prefix in tables:
                try:
                    cur.execute(
                        f"SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja FROM {table_name} WHERE id=%s",
                        (surowiec_id,)
                    )
                    row = cur.fetchone()
                    if row:
                        nr_palety = (row.get('nr_palety') or '').strip()
                        return {
                            'id': row['id'],
                            'nr_palety': nr_palety,
                            'nazwa': row['nazwa'],
                            'ilosc': float(row['stan_magazynowy'] or 0),
                            'lokalizacja': row.get('lokalizacja') or '',
                            'qr_data': f"{nr_palety}|{row.get('lokalizacja') or ''}|{row['nazwa']}" if nr_palety else f"{prefix}-{row['id']}|{row.get('lokalizacja') or ''}|{row['nazwa']}",
                            'data': datetime.now().strftime('%d.%m.%Y %H:%M'),
                        }
                except Exception:
                    pass
            return None
        finally:
            conn.close()


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
    location_fallback: str = '',
) -> dict:
    qty = float(row.get('ilosc', row.get('stan_magazynowy', 0)) or 0)
    location = str(row.get('lokalizacja') or location_fallback or '').strip().upper()

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
        'can_dispatch': bool(can_dispatch),
        'can_split': bool(can_split),
        'can_print_label': bool(can_print_label),
        'unit': 'kg',
    }
