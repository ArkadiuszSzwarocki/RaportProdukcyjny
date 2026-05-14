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
import re


class ScannerService:
    SCAN_TOKEN_PATTERN = re.compile(
        r'(R\d{6}|SUR-\d+|OPK-\d+|DOD-\d+|PAL-\d+|MS01|MP01|MDM01|MOP01|MGW01|MGW02|OS\d{2}|OSIP|BB\d{2}|MZ\d{2}(?:-\d{2})?|BF_MS01|BF_MP01|KO01|PSD01|PSD|RAMPA|MIX01|W_TRANZYCIE_OSIP)',
        re.IGNORECASE,
    )

    @staticmethod
    def _normalize_scanned_code(raw_code: str) -> str:
        code = str(raw_code or '').strip().upper()
        if not code:
            return ''

        code = re.sub(r'[\r\n\t]+', ' ', code).strip()

        # Zebra zwykle wysyła czysty tekst + Enter, ale część etykiet QR może mieć prefixy/URL.
        match = ScannerService.SCAN_TOKEN_PATTERN.search(code)
        if match:
            return match.group(1).upper()

        return code

    @staticmethod
    def _extract_prefixed_id(code: str) -> tuple[str | None, int | None]:
        match = re.match(r'^(SUR|OPK|DOD|PAL)-(\d+)$', str(code or '').strip().upper())
        if not match:
            return None, None
        return match.group(1), int(match.group(2))

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

        sql = (
            f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, COALESCE(lokalizacja, '') AS lokalizacja "
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
                f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, '' AS lokalizacja "
                f"FROM {table_name} WHERE COALESCE({qty_col}, 0) > 0 AND id = %s LIMIT 1"
            )
            try:
                cur.execute(fallback_sql, (item_id,))
                return cur.fetchone()
            except Exception:
                return None

    @staticmethod
    def _lookup_finished_goods(cur, linia: str, *, item_id: int | None = None, location_code: str | None = None) -> dict | None:
        table_name = get_table_name('magazyn_palety', linia)

        if item_id is not None:
            try:
                cur.execute(
                    f"SELECT id, produkt AS nazwa, waga_netto AS ilosc, 'MGW01' AS lokalizacja "
                    f"FROM {table_name} WHERE id = %s AND COALESCE(waga_netto, 0) > 0 LIMIT 1",
                    (item_id,),
                )
                return cur.fetchone()
            except Exception:
                return None

        normalized_location = str(location_code or '').strip().upper()
        if normalized_location not in {'MGW01', 'MGW02'}:
            return None

        try:
            cur.execute(
                f"SELECT id, produkt AS nazwa, waga_netto AS ilosc, %s AS lokalizacja "
                f"FROM {table_name} WHERE COALESCE(waga_netto, 0) > 0 "
                "ORDER BY COALESCE(data_potwierdzenia, created_at) DESC, id DESC LIMIT 1",
                (normalized_location,),
            )
            return cur.fetchone()
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # LOOKUP — znajdź paletę po lokalizacji lub ID
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def lookup_by_location(location_code: str, linia: str = 'Agro') -> dict | None:
        """Zwraca dane pozycji magazynowej dla kodu lokalizacji lub ID.

        Obsługiwane prefiksy: SUR-, OPK-, DOD-, PAL- oraz kody lokalizacji.
        Returns None jeśli nie znaleziono pozycji z ilością > 0.
        """
        location_code = ScannerService._normalize_scanned_code(location_code)
        if not location_code:
            return None

        prefixed_type, prefixed_id = ScannerService._extract_prefixed_id(location_code)

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

            if prefixed_type:
                prefixed_row = None
                if prefixed_type == 'PAL':
                    prefixed_row = ScannerService._lookup_finished_goods(cur, linia, item_id=prefixed_id)
                    if prefixed_row:
                        return _normalize_lookup_item(
                            prefixed_row,
                            inventory_type='Wyrób Gotowy',
                            inventory_key='WYROB_GOTOWY',
                            code_prefix='PAL',
                            can_dispatch=False,
                            can_split=False,
                            can_print_label=False,
                            location_fallback='MGW01',
                        )
                    return None

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
                        return _normalize_lookup_item(
                            prefixed_row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        )
                    return None

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
                    return _normalize_lookup_item(
                        row,
                        inventory_type=inv_type,
                        inventory_key=code_prefix,
                        code_prefix=code_prefix,
                        can_dispatch=can_dispatch,
                        can_split=can_split,
                        can_print_label=can_print,
                    )

            # 2) Lookup lokalizacji MGW01/MGW02 dla wyrobów gotowych.
            row = ScannerService._lookup_finished_goods(cur, linia, location_code=location_code)
            if row:
                return _normalize_lookup_item(
                    row,
                    inventory_type='Wyrób Gotowy',
                    inventory_key='WYROB_GOTOWY',
                    code_prefix='PAL',
                    can_dispatch=False,
                    can_split=False,
                    can_print_label=False,
                    location_fallback=location_code,
                )

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
                        return _normalize_lookup_item(
                            row,
                            inventory_type=inv_type,
                            inventory_key=code_prefix,
                            code_prefix=code_prefix,
                            can_dispatch=can_dispatch,
                            can_split=can_split,
                            can_print_label=can_print,
                        )

                row = ScannerService._lookup_finished_goods(cur, linia, item_id=numeric_id)
                if row:
                    return _normalize_lookup_item(
                        row,
                        inventory_type='Wyrób Gotowy',
                        inventory_key='WYROB_GOTOWY',
                        code_prefix='PAL',
                        can_dispatch=False,
                        can_split=False,
                        can_print_label=False,
                        location_fallback='MGW01',
                    )

            return None
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
    ) -> tuple[bool, str]:
        """Pobiera `ilosc` kg z palety (surowiec_id) na produkcję.

        Returns (success, message)
        """
        if ilosc <= 0:
            return False, "Ilość musi być > 0"

        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch    = get_table_name('magazyn_ruch',    linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            pallet = cur.fetchone()
            if not pallet:
                return False, f"Paleta #{surowiec_id} nie istnieje"

            stan = float(pallet['stan_magazynowy'] or 0)
            if ilosc > stan:
                return False, f"Za duża ilość — dostępne: {stan:.1f} kg"

            now = datetime.now()
            plan_id_val   = int(plan_id) if plan_id not in (None, '', 0, '0') else None
            zbiornik_val  = zbiornik.strip() if zbiornik and str(zbiornik).strip() else None

            # Zmniejsz stan
            cur.execute(
                f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy - %s WHERE id = %s",
                (ilosc, surowiec_id)
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
                    pallet.get('lokalizacja'),
                    worker_login, now, worker_login, now,
                    plan_id_val, komentarz, zbiornik_val
                )
            )
            conn.commit()
            return True, f"Przekazano {ilosc:.1f} kg [{pallet['nazwa']}] na produkcję. Pozostało: {stan_po:.1f} kg"
        except Exception as e:
            conn.rollback()
            return False, f"Błąd: {e}"
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # SPLIT — podziel paletę na N worków
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def split_pallet(
        surowiec_id: int,
        bags: list[dict],
        worker_login: str,
        linia: str = 'Agro',
    ) -> tuple[bool, str, list[dict]]:
        """Dzieli jedną paletę na kilka mniejszych rekordów (worków).

        Args:
            surowiec_id: ID palety źródłowej
            bags: lista dict { 'ilosc': float, 'lokalizacja': str }
                  Suma ilości MUSI być <= stan_magazynowy palety źródłowej.
            worker_login: kto wykonuje operację
            linia: linia produkcyjna / magazyn

        Returns:
            (success, message, new_pallet_ids)
            new_pallet_ids — lista dict {id, nazwa, ilosc, lokalizacja}
        """
        if not bags:
            return False, "Brak worków do podziału", []

        total_split = sum(float(b.get('ilosc', 0)) for b in bags)
        if total_split <= 0:
            return False, "Suma worków musi być > 0", []

        table_surowce = get_table_name('magazyn_surowce', linia)
        table_ruch    = get_table_name('magazyn_ruch',    linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            source = cur.fetchone()
            if not source:
                return False, f"Paleta #{surowiec_id} nie istnieje", []

            stan = float(source['stan_magazynowy'] or 0)
            if total_split > stan + 0.001:
                return False, f"Suma worków ({total_split:.1f} kg) > stan palety ({stan:.1f} kg)", []

            now = datetime.now()
            new_records: list[dict] = []

            # Sprawdź unikalnos lokalizacji
            locations = [b.get('lokalizacja', '').strip().upper() for b in bags]
            locations_non_empty = [l for l in locations if l]
            if len(locations_non_empty) != len(set(locations_non_empty)):
                return False, "Lokalizacje worków muszą być unikalne", []

            # Sprawdź czy lokalizacje wolne
            for loc in locations_non_empty:
                cur.execute(
                    f"SELECT id FROM {table_surowce} WHERE UPPER(lokalizacja)=%s AND stan_magazynowy>0 AND id!=%s",
                    (loc, surowiec_id)
                )
                if cur.fetchone():
                    return False, f"Lokalizacja {loc} jest zajęta", []

            # 1. Zeruj paletę źródłową
            remaining = round(stan - total_split, 3)
            if remaining > 0.01:
                # zostaw resztę na pierwotnej lokalizacji
                cur.execute(
                    f"UPDATE {table_surowce} SET stan_magazynowy=%s WHERE id=%s",
                    (remaining, surowiec_id)
                )
                cur.execute(
                    f"INSERT INTO {table_ruch} "
                    "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                    "autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                    "VALUES (%s,%s,'KOREKTA',%s,%s,%s,'POTWIERDZONE',%s,%s,%s,%s,%s)",
                    (
                        surowiec_id, source['nazwa'],
                        -total_split, remaining, source.get('lokalizacja'),
                        worker_login, now, worker_login, now,
                        f"Podział palety na {len(bags)} worki — reszta {remaining:.1f} kg"
                    )
                )
            else:
                # Zeruj paletę całkowicie
                cur.execute(
                    f"UPDATE {table_surowce} SET stan_magazynowy=0 WHERE id=%s",
                    (surowiec_id,)
                )
                cur.execute(
                    f"INSERT INTO {table_ruch} "
                    "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                    "autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                    "VALUES (%s,%s,'KOREKTA',%s,0,%s,'POTWIERDZONE',%s,%s,%s,%s,%s)",
                    (
                        surowiec_id, source['nazwa'],
                        -stan, source.get('lokalizacja'),
                        worker_login, now, worker_login, now,
                        f"Podział palety na {len(bags)} worki — paleta zerowana"
                    )
                )

            # 2. Utwórz nowe palety/worki
            for i, bag in enumerate(bags):
                bag_qty  = float(bag.get('ilosc', 0))
                bag_loc  = bag.get('lokalizacja', '').strip().upper() or None
                bag_name = bag.get('nazwa', source['nazwa'])  # można nadać inną nazwę

                cur.execute(
                    f"INSERT INTO {table_surowce} (nazwa, stan_magazynowy, lokalizacja) VALUES (%s,%s,%s)",
                    (bag_name, bag_qty, bag_loc)
                )
                new_id = cur.lastrowid

                cur.execute(
                    f"INSERT INTO {table_ruch} "
                    "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, "
                    "autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                    "VALUES (%s,%s,'PRZYJECIE',%s,%s,%s,'POTWIERDZONE',%s,%s,%s,%s,%s)",
                    (
                        new_id, bag_name, bag_qty, bag_qty, bag_loc,
                        worker_login, now, worker_login, now,
                        f"Worek {i+1}/{len(bags)} z podziału palety #{surowiec_id}"
                    )
                )
                new_records.append({
                    'id': new_id,
                    'nazwa': bag_name,
                    'ilosc': bag_qty,
                    'lokalizacja': bag_loc or '',
                })

            conn.commit()
            return True, f"Podzielono na {len(bags)} worków. Nowe ID: {[r['id'] for r in new_records]}", new_records

        except Exception as e:
            conn.rollback()
            return False, f"Błąd podziału: {e}", []
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # QR label data — dane do wydruku etykiety
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_label_data(surowiec_id: int, linia: str = 'Agro') -> dict | None:
        """Zwraca słownik danych potrzebnych do wydruku etykiety ZPL."""
        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja FROM {table_surowce} WHERE id=%s",
                (surowiec_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                'id': row['id'],
                'nazwa': row['nazwa'],
                'ilosc': float(row['stan_magazynowy'] or 0),
                'lokalizacja': row.get('lokalizacja') or '',
                'qr_data': f"SUR-{row['id']}|{row.get('lokalizacja') or ''}|{row['nazwa']}",
                'data': datetime.now().strftime('%d.%m.%Y %H:%M'),
            }
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

    return {
        'id': row['id'],
        'nazwa': row.get('nazwa') or '',
        'stan_magazynowy': qty,
        'lokalizacja': location,
        'inventory_type': inventory_type,
        'inventory_key': inventory_key,
        'inventory_code': f"{code_prefix}-{row['id']}",
        'can_dispatch': bool(can_dispatch),
        'can_split': bool(can_split),
        'can_print_label': bool(can_print_label),
        'unit': 'kg',
    }
