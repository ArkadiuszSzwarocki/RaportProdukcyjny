from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.db import get_db_connection, get_table_name
from app.services.scanner.scanner_code_normalizer import normalize_scanned_code
from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id

class ScannerLabelService:
    """Obsługuje pobieranie i formatowanie danych do wydruku etykiet ZPL i kodów QR."""

    @staticmethod
    def get_label_data(identifier: str | int, linia: str = 'Agro', pallet_type: str | None = None) -> dict | None:
        """Zwraca słownik danych potrzebnych do wydruku etykiety ZPL."""
        if not identifier:
            return None

        clean_id_str = str(identifier).strip()
        sscc_code = normalize_scanned_code(clean_id_str)
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

            # 2. Definicja tabel i priorytetów wyszukiwania
            tables = [
                (get_table_name('magazyn_palety', linia), 'waga_netto', 'COALESCE(produkt, nazwa)', 'WYRÓB GOTOWY', 'PAL', True),
                (get_table_name('magazyn_surowce', linia), 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', False),
                (get_table_name('magazyn_opakowania', linia), 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', False),
                ('magazyn_dodatki', 'stan_magazynowy', 'nazwa', 'DODATEK', 'DOD', False),
                ('magazyn_palety', 'waga_netto', 'COALESCE(produkt, nazwa)', 'WYRÓB GOTOWY', 'PAL', True),
                ('magazyn_palety_agro', 'waga_netto', 'COALESCE(produkt, nazwa)', 'WYRÓB GOTOWY', 'PAL', True),
                ('magazyn_surowce', 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', False),
                ('magazyn_surowce_agro', 'stan_magazynowy', 'nazwa', 'SUROWIEC', 'SUR', False),
                ('magazyn_opakowania', 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', False),
                ('magazyn_opakowania_agro', 'stan_magazynowy', 'nazwa', 'OPAKOWANIE', 'OPK', False),
                ('palety_agro', 'waga', 'produkt', 'WYRÓB GOTOWY', 'PAL', True),
                ('palety_workowanie', 'waga', 'produkt', 'WYRÓB GOTOWY', 'PAL', True)
            ]

            seen_tables = set()

            if sscc_code:
                for table_name, qty_col, name_col, typ_name, prefix, is_fg in tables:
                    if table_name in seen_tables:
                        continue
                    seen_tables.add(table_name)
                    try:
                        sql = (
                            f"SELECT id, nr_palety, {name_col} as nazwa, {qty_col} as stan_magazynowy, "
                            f"COALESCE(lokalizacja, '') as lokalizacja, COALESCE(nr_partii, '') as nr_partii, "
                            f"data_produkcji, data_przydatnosci "
                            f"FROM {table_name} WHERE UPPER(COALESCE(nr_palety, '')) = %s ORDER BY id DESC LIMIT 1"
                        )
                        cur.execute(sql, (sscc_code.upper(),))
                        row = cur.fetchone()
                        if row:
                            return ScannerLabelService.build_label_dict(cur, row, linia, prefix, typ_name, is_fg)
                    except Exception:
                        pass

            if numeric_id is not None:
                seen_tables.clear()
                for table_name, qty_col, name_col, typ_name, prefix, is_fg in tables:
                    if table_name in seen_tables:
                        continue
                    seen_tables.add(table_name)
                    try:
                        sql = (
                            f"SELECT id, nr_palety, {name_col} as nazwa, {qty_col} as stan_magazynowy, "
                            f"COALESCE(lokalizacja, '') as lokalizacja, COALESCE(nr_partii, '') as nr_partii, "
                            f"data_produkcji, data_przydatnosci "
                            f"FROM {table_name} WHERE id = %s LIMIT 1"
                        )
                        cur.execute(sql, (numeric_id,))
                        row = cur.fetchone()
                        if row:
                            return ScannerLabelService.build_label_dict(cur, row, linia, prefix, typ_name, is_fg)
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
        
        if not is_fg and qty <= 0:
            from app.services.scanner_service import ScannerService
            prod_qty, prod_tank = ScannerService._get_active_production_qty(cur, row['id'], linia)
            if prod_qty > 0:
                qty = prod_qty
                if prod_tank:
                    row['lokalizacja'] = prod_tank

        dp = row.get('data_produkcji')
        dp_str = dp.strftime('%Y-%m-%d') if hasattr(dp, 'strftime') else (str(dp) if dp else datetime.now().strftime('%Y-%m-%d'))

        dz = row.get('data_przydatnosci')
        dz_str = dz.strftime('%Y-%m-%d') if hasattr(dz, 'strftime') else (str(dz) if dz else '---')

        jednostka = 'szt.' if typ_name == 'OPAKOWANIE' else 'kg'

        return {
            'id': row['id'],
            'nr_palety': nr_palety,
            'sscc': nr_palety,
            'nazwa': row.get('nazwa') or 'Brak nazwy',
            'ilosc': qty,
            'lokalizacja': row.get('lokalizacja') or '',
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
            'qr_data': f"{nr_palety}|{row.get('lokalizacja') or ''}|{row.get('nazwa') or ''}"
        }
