"""Location and multi-criteria scanner query coordinator."""
from __future__ import annotations

import re
from app.core.database import get_db_connection, get_table_name
from app.services.scanner.scanner_code_normalizer import ScannerCodeNormalizer
from app.services.scanner.scanner_item_normalizer import ScannerItemNormalizer
from app.services.scanner.scanner_lookup_service import ScannerLookupService


class ScannerLocationQueryService:
    """Coordinates pallet and shelf lookups across lines and tables."""

    @staticmethod
    def lookup_by_location_internal(location_code: str, linia: str) -> list[dict]:
        location_code = ScannerCodeNormalizer.normalize_scanned_code(location_code)
        if not location_code:
            return []

        is_sscc_flag = ScannerCodeNormalizer.is_sscc_code(location_code)

        # Regał R09
        if not is_sscc_flag and location_code.startswith('R09'):
            conn = get_db_connection()
            try:
                cur = conn.cursor(dictionary=True)
                items = []
                inventory_sources_shelf = [
                    ('magazyn_surowce', 'stan_magazynowy', 'nazwa', 'Surowiec', 'SUR', True, True, True),
                    ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'Opakowanie', 'OPK', False, False, True),
                    ('magazyn_dodatki', 'stan_magazynowy', 'nazwa', 'Dodatek', 'DOD', False, False, True),
                    ('magazyn_palety', 'waga_netto', 'COALESCE(produkt, nazwa)', 'Wyrób Gotowy', 'PAL', False, False, True),
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
                            items.append(ScannerItemNormalizer.normalize_lookup_item(
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
                ('magazyn_palety', 'waga_netto', 'COALESCE(produkt, nazwa)', 'Wyrób Gotowy', 'PAL', False, False, True),
                ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'Opakowanie', 'OPK', False, False, True),
                ('magazyn_dodatki', 'stan_magazynowy', 'nazwa', 'Dodatek', 'DOD', False, False, True),
            ]
            
            for base_table, qty_col, name_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                table_name = get_table_name(base_table, linia)
                try:
                    sql = (
                        f"SELECT id, {qty_col} AS ilosc, {name_col} AS nazwa, COALESCE(lokalizacja, '') AS lokalizacja, "
                        f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                        f"data_produkcji, data_przydatnosci "
                        f"FROM {table_name} WHERE UPPER(COALESCE(nr_palety, '')) = %s ORDER BY {qty_col} DESC, id DESC"
                    )
                    cur.execute(sql, (normalized_for_lookup,))
                    rows = cur.fetchall()
                    for row in rows:
                        if base_table == 'magazyn_surowce' and float(row.get('ilosc') or 0) <= 0:
                            prod_qty, prod_tank = ScannerLookupService.get_active_production_qty(cur, row['id'], linia)
                            if prod_qty > 0:
                                row['ilosc'] = prod_qty
                                if prod_tank:
                                    row['lokalizacja'] = prod_tank
                        results.append(ScannerItemNormalizer.normalize_lookup_item(
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
            
            is_raw_pallet_check = ScannerCodeNormalizer.is_sscc_code(location_code) or bool(re.match(r'^SUR-?\d+$', location_code, re.I))
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
                        prod_qty, prod_tank = ScannerLookupService.get_active_production_qty(cur, s_id, linia)
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
                        items.append(ScannerItemNormalizer.normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        ))
                
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

                return [{
                    'is_station': True,
                    'station_code': location_code,
                    'items': items
                }]

            finally:
                conn.close()

        prefixed_type, prefixed_id = ScannerCodeNormalizer.extract_prefixed_id(location_code)
        is_sscc = ScannerCodeNormalizer.is_sscc_code(location_code)
        is_partial_sscc = location_code.isdigit() and len(location_code) >= 5

        numeric_id = prefixed_id if prefixed_id is not None else (int(location_code) if location_code.isdigit() else None)

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
                        cur.execute(
                            f"SELECT p.id, p.nr_palety, p.waga, plan.produkt as nazwa, plan.data_produkcji, NULL as nr_partii, NULL as data_przydatnosci "
                            f"FROM {table_prod} p "
                            f"LEFT JOIN {table_plan} plan ON p.plan_id = plan.id "
                            f"WHERE (p.id = %s OR UPPER(COALESCE(p.nr_palety,'')) = %s) AND p.status = 'do_przyjecia'",
                            (numeric_lookup, location_code)
                        )
                    else:
                        pattern = ('%' + location_code) if (is_partial_sscc and not is_sscc) else location_code
                        op = 'LIKE' if (is_partial_sscc and not is_sscc) else '='
                        cur.execute(
                            f"SELECT p.id, p.nr_palety, p.waga, plan.produkt as nazwa, plan.data_produkcji, NULL as nr_partii, NULL as data_przydatnosci "
                            f"FROM {table_prod} p "
                            f"LEFT JOIN {table_plan} plan ON p.plan_id = plan.id "
                            f"WHERE UPPER(COALESCE(p.nr_palety,'')) {op} %s AND p.status = 'do_przyjecia'",
                            (pattern,)
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
                    prefixed_row = ScannerLookupService.lookup_finished_goods(cur, linia, item_id=prefixed_id)
                    if prefixed_row:
                        results.append(ScannerItemNormalizer.normalize_lookup_item(
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
                    prefixed_row = ScannerLookupService.lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        item_id=prefixed_id,
                    )
                    if prefixed_row:
                        val = ScannerItemNormalizer.normalize_lookup_item(
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
                    sscc_row = ScannerLookupService.lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        pallet_no=location_code if (is_sscc or is_new_pallet_format) else None,
                        partial_pallet_no=location_code if is_partial_sscc and not is_sscc and not is_new_pallet_format else None,
                    )
                    if sscc_row:
                        val = ScannerItemNormalizer.normalize_lookup_item(
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

                fg_row = ScannerLookupService.lookup_finished_goods(
                    cur, 
                    linia, 
                    pallet_no=location_code if (is_sscc or is_new_pallet_format) else None,
                    partial_pallet_no=location_code if is_partial_sscc and not is_sscc and not is_new_pallet_format else None,
                )
                if fg_row:
                    val = ScannerItemNormalizer.normalize_lookup_item(
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

            for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                row = ScannerLookupService.lookup_inventory_row(
                    cur,
                    base_table,
                    linia,
                    qty_col=qty_col,
                    location_code=location_code,
                )
                if row:
                    val = ScannerItemNormalizer.normalize_lookup_item(
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

            row = ScannerLookupService.lookup_finished_goods(cur, linia, location_code=location_code)
            if row:
                val = ScannerItemNormalizer.normalize_lookup_item(
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

            if prefixed_type is None:
                row = ScannerLookupService.lookup_finished_goods(cur, linia, pallet_no=location_code)
                if row:
                    val = ScannerItemNormalizer.normalize_lookup_item(
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

            if numeric_id is not None:
                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    row = ScannerLookupService.lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        item_id=numeric_id,
                    )
                    if row:
                        val = ScannerItemNormalizer.normalize_lookup_item(
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

                row = ScannerLookupService.lookup_finished_goods(cur, linia, item_id=numeric_id)
                if row:
                    val = ScannerItemNormalizer.normalize_lookup_item(
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

            if not results and re.match(r'^\d{6}$', location_code):
                rack_with_r = f"R{location_code}"
                for base_table, qty_col, inv_type, code_prefix, can_dispatch, can_split, can_print in inventory_sources:
                    row = ScannerLookupService.lookup_inventory_row(
                        cur,
                        base_table,
                        linia,
                        qty_col=qty_col,
                        location_code=rack_with_r,
                    )
                    if row:
                        results.append(ScannerItemNormalizer.normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        ))
                        return results

                row = ScannerLookupService.lookup_finished_goods(cur, linia, location_code=rack_with_r)
                if row:
                    results.append(ScannerItemNormalizer.normalize_lookup_item(
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
