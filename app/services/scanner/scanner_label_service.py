import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.db import get_db_connection, get_table_name
from app.services.scanner.scanner_code_normalizer import ScannerCodeNormalizer
from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id


class ScannerLabelService:
    """Obsługuje pobieranie i formatowanie danych do wydruku etykiet ZPL i kodów QR."""

    @staticmethod
    def get_label_data(identifier: str | int, linia: str = 'Agro', pallet_type: str | None = None) -> dict | None:
        """Zwraca słownik danych potrzebnych do wydruku etykiety ZPL.
        Zgodnie z wymogami systemu ZAWSZE szuka w pierwszej kolejności po unikalnym numerze SSCC (nr_palety).
        """
        if not identifier:
            return None

        clean_id_str = str(identifier).strip()
        sscc_code = ScannerCodeNormalizer.normalize_scanned_code(clean_id_str)
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

            is_agro = (str(linia).upper() == 'AGRO')
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
                # 1. Sprawdź wyroby gotowe
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
                            return ScannerLabelService.build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
                    except Exception:
                        pass

                # 2. Palety produkcyjne
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
                            return ScannerLabelService.build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
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
                            return ScannerLabelService.build_label_dict(cur, row, item_line, prefix, typ_name, False)
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
                            return ScannerLabelService.build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
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
                            return ScannerLabelService.build_label_dict(cur, row, item_line, prefix, typ_name, False)
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
                            return ScannerLabelService.build_label_dict(cur, row, item_line, 'PAL', 'WYRÓB GOTOWY', True)
                    except Exception:
                        pass

            return None
        finally:
            conn.close()

    @staticmethod
    def build_label_dict(cur, row: dict, linia: str, prefix: str, typ_name: str, is_fg: bool) -> dict:
        nr_palety = (row.get('nr_palety') or '').strip()
        if not nr_palety or not is_valid_pallet_id(nr_palety):
            nr_palety = generate_pallet_id(linia, typ_name.lower())
            row['nr_palety'] = nr_palety
        qty = float(row.get('stan_magazynowy') or 0)
        
        # Jeśli surowiec jest na stacji produkcyjnej, sprawdź aktualny stan ze stacji
        if not is_fg and qty <= 0:
            from app.services.scanner.scanner_lookup_service import ScannerLookupService
            prod_qty, prod_tank = ScannerLookupService.get_active_production_qty(cur, row['id'], linia)
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
