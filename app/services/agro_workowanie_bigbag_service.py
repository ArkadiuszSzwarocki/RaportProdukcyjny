"""
agro_workowanie_bigbag_service.py — Obsługa wsadu z Big Bagów na sekcji Workowanie AGRO.

Umożliwia:
- Skanowanie i identyfikację Big Bagów (surowce i wyroby gotowe w magazynie),
- Rozchodowanie Big Bagów do zlecenia workowania (PRODUKCJA),
- Wyliczenie bilansu wsadu z Big Bagów vs spakowane palety na żywo,
- Wycofanie/zwrot Big Baga z powrotem na stan magazynu.
"""

from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from app.db import get_db_connection, get_table_name
from app.services.scanner_service import ScannerService


class AgroWorkowanieBigBagService:
    @staticmethod
    def lookup_bigbag(code: str, linia: str = 'AGRO', auto_reconcile: bool = True) -> Optional[Dict[str, Any]]:
        """Wyszukuje aktywną paletę/Big Bag w magazynie surowców lub wyrobów gotowych."""
        if not code:
            return None

        raw_code = str(code).strip()
        normalized = ScannerService._normalize_scanned_code(raw_code)
        if not normalized:
            normalized = raw_code.upper()

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            prefix, item_id = ScannerService._extract_prefixed_id(normalized)

            # Jeśli wpisano czysty integer o długości < 10, traktuj jako jawne ID palety
            if not item_id and raw_code.isdigit() and len(raw_code) < 10:
                try:
                    item_id = int(raw_code)
                except ValueError:
                    item_id = None

            import re
            digits_only = re.sub(r'\D', '', normalized)

            lines_to_check = ['AGRO', 'PSD'] if linia.upper() == 'AGRO' else ['PSD', 'AGRO']

            def _format_row(row):
                dp = row.get('data_produkcji')
                dp_str = dp.strftime('%Y-%m-%d') if hasattr(dp, 'strftime') else (str(dp) if dp else '')
                dz = row.get('data_przydatnosci')
                dz_str = dz.strftime('%Y-%m-%d') if hasattr(dz, 'strftime') else (str(dz) if dz else '')
                res = {
                    'id': row['id'],
                    'nr_palety': row.get('nr_palety') or f"PAL-{row['id']}",
                    'nazwa': row.get('nazwa') or ('Surowiec' if row.get('typ_palety') == 'Surowiec' else 'Wyrób Gotowy'),
                    'waga': float(row.get('stan_magazynowy') or 0),
                    'lokalizacja': row.get('lokalizacja') or 'Magazyn',
                    'nr_partii': row.get('nr_partii') or 'BRAK',
                    'data_produkcji': dp_str,
                    'data_przydatnosci': dz_str,
                    'is_blocked': bool(row.get('is_blocked')),
                    'typ_palety': row.get('typ_palety'),
                    'linia': row.get('linia'),
                    'table_name': row.get('table_name'),
                    'qty_column': row.get('qty_column')
                }
                if res['is_blocked'] and auto_reconcile:
                    try:
                        from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
                        if PalletLockManager.reconcile_orphan_transfer_locks() > 0:
                            refreshed = AgroWorkowanieBigBagService.lookup_bigbag(code, linia=linia, auto_reconcile=False)
                            if refreshed:
                                return refreshed
                    except Exception:
                        pass
                return res

            # KROK 1: Jeśli podano ID z prefiksem (np. PAL-2253, SUR-3819)
            if prefix and item_id:
                if prefix in ('PAL', 'AGR', 'PSD'):
                    for l in lines_to_check:
                        tbl_pal = get_table_name('magazyn_palety', l)
                        tbl_plan = get_table_name('plan_produkcji', l)
                        query = f"""
                            SELECT m.id, m.nr_palety,
                                   COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób gotowy') as nazwa,
                                   m.waga_netto as stan_magazynowy,
                                   COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as lokalizacja,
                                   COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, 'BRAK') as nr_partii,
                                   COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji) as data_produkcji,
                                   COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                                   m.is_blocked, '{l}' as linia, 'Wyrób Gotowy' as typ_palety, '{tbl_pal}' as table_name,
                                   'waga_netto' as qty_column
                            FROM {tbl_pal} m
                            LEFT JOIN {tbl_plan} plan ON m.plan_id = plan.id
                            WHERE m.id = %s
                        """
                        cursor.execute(query, (item_id,))
                        row = cursor.fetchone()
                        if row:
                            return _format_row(row)

                if prefix == 'SUR':
                    for l in lines_to_check:
                        tbl_sur = get_table_name('magazyn_surowce', l)
                        query = f"""
                            SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                                   data_produkcji, data_przydatnosci, is_blocked, '{l}' as linia,
                                   'Surowiec' as typ_palety, '{tbl_sur}' as table_name,
                                   'stan_magazynowy' as qty_column
                            FROM {tbl_sur}
                            WHERE id = %s
                        """
                        cursor.execute(query, (item_id,))
                        row = cursor.fetchone()
                        if row:
                            return _format_row(row)

            # KROK 2: DOKŁADNE dopasowanie po pełnym nr_palety (Exact match)
            for l in lines_to_check:
                tbl_pal = get_table_name('magazyn_palety', l)
                tbl_plan = get_table_name('plan_produkcji', l)
                query = f"""
                    SELECT m.id, m.nr_palety,
                           COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób gotowy') as nazwa,
                           m.waga_netto as stan_magazynowy,
                           COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as lokalizacja,
                           COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, 'BRAK') as nr_partii,
                           COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji) as data_produkcji,
                           COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                           m.is_blocked, '{l}' as linia, 'Wyrób Gotowy' as typ_palety, '{tbl_pal}' as table_name,
                           'waga_netto' as qty_column
                    FROM {tbl_pal} m
                    LEFT JOIN {tbl_plan} plan ON m.plan_id = plan.id
                    WHERE UPPER(m.nr_palety) = %s OR (
                        %s != '' AND (
                            m.nr_palety = %s OR m.nr_palety = CONCAT('AGR', %s) OR m.nr_palety = CONCAT('PSD', %s)
                        )
                    )
                    ORDER BY (m.waga_netto > 0) DESC, (m.is_blocked = 0) DESC, m.id DESC LIMIT 1
                """
                cursor.execute(query, (normalized, digits_only, digits_only, digits_only, digits_only))
                row = cursor.fetchone()
                if row:
                    return _format_row(row)

            for l in lines_to_check:
                tbl_sur = get_table_name('magazyn_surowce', l)
                query = f"""
                    SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                           data_produkcji, data_przydatnosci, is_blocked, '{l}' as linia,
                           'Surowiec' as typ_palety, '{tbl_sur}' as table_name,
                           'stan_magazynowy' as qty_column
                    FROM {tbl_sur}
                    WHERE UPPER(nr_palety) = %s OR (
                        %s != '' AND (
                            nr_palety = %s OR nr_palety = CONCAT('SUR', %s)
                        )
                    )
                    ORDER BY (stan_magazynowy > 0) DESC, (is_blocked = 0) DESC, id DESC LIMIT 1
                """
                cursor.execute(query, (normalized, digits_only, digits_only, digits_only))
                row = cursor.fetchone()
                if row:
                    return _format_row(row)

            # KROK 3: Jeśli wpisano czyste ID (np. 2253, 2255, 2262)
            if item_id:
                for l in lines_to_check:
                    tbl_pal = get_table_name('magazyn_palety', l)
                    tbl_plan = get_table_name('plan_produkcji', l)
                    query = f"""
                        SELECT m.id, m.nr_palety,
                               COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób gotowy') as nazwa,
                               m.waga_netto as stan_magazynowy,
                               COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as lokalizacja,
                               COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, 'BRAK') as nr_partii,
                               COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji) as data_produkcji,
                               COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                               m.is_blocked, '{l}' as linia, 'Wyrób Gotowy' as typ_palety, '{tbl_pal}' as table_name,
                               'waga_netto' as qty_column
                        FROM {tbl_pal} m
                        LEFT JOIN {tbl_plan} plan ON m.plan_id = plan.id
                        WHERE m.id = %s
                    """
                    cursor.execute(query, (item_id,))
                    row = cursor.fetchone()
                    if row:
                        return _format_row(row)

                for l in lines_to_check:
                    tbl_sur = get_table_name('magazyn_surowce', l)
                    query = f"""
                        SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                               data_produkcji, data_przydatnosci, is_blocked, '{l}' as linia,
                               'Surowiec' as typ_palety, '{tbl_sur}' as table_name,
                               'stan_magazynowy' as qty_column
                        FROM {tbl_sur}
                        WHERE id = %s
                    """
                    cursor.execute(query, (item_id,))
                    row = cursor.fetchone()
                    if row:
                        return _format_row(row)

            # KROK 4: Dopasowanie po końcówce kodu (Suffix match - np. ze skanera)
            if len(digits_only) >= 6:
                for l in lines_to_check:
                    tbl_pal = get_table_name('magazyn_palety', l)
                    tbl_plan = get_table_name('plan_produkcji', l)
                    query = f"""
                        SELECT m.id, m.nr_palety,
                               COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób gotowy') as nazwa,
                               m.waga_netto as stan_magazynowy,
                               COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as lokalizacja,
                               COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, 'BRAK') as nr_partii,
                               COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji) as data_produkcji,
                               COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                               m.is_blocked, '{l}' as linia, 'Wyrób Gotowy' as typ_palety, '{tbl_pal}' as table_name,
                               'waga_netto' as qty_column
                        FROM {tbl_pal} m
                        LEFT JOIN {tbl_plan} plan ON m.plan_id = plan.id
                        WHERE m.nr_palety LIKE %s
                        ORDER BY (m.waga_netto > 0) DESC, (m.is_blocked = 0) DESC, m.id DESC LIMIT 1
                    """
                    cursor.execute(query, (f"%{digits_only}",))
                    row = cursor.fetchone()
                    if row:
                        return _format_row(row)

                for l in lines_to_check:
                    tbl_sur = get_table_name('magazyn_surowce', l)
                    query = f"""
                        SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                               data_produkcji, data_przydatnosci, is_blocked, '{l}' as linia,
                               'Surowiec' as typ_palety, '{tbl_sur}' as table_name,
                               'stan_magazynowy' as qty_column
                        FROM {tbl_sur}
                        WHERE nr_palety LIKE %s
                        ORDER BY (stan_magazynowy > 0) DESC, (is_blocked = 0) DESC, id DESC LIMIT 1
                    """
                    cursor.execute(query, (f"%{digits_only}",))
                    row = cursor.fetchone()
                    if row:
                        return _format_row(row)

            return None
        finally:
            conn.close()

    @staticmethod
    def add_bigbag_to_plan(
        plan_id: int,
        code: str,
        worker_login: str,
        linia: str = 'AGRO',
        ilosc: Optional[float] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Dodaje wskanowany Big Bag do zlecenia workowania i zdejmuje stan z magazynu."""
        if not plan_id or not code:
            return False, "Brak numeru zlecenia lub kodu Big Baga.", None

        pallet = AgroWorkowanieBigBagService.lookup_bigbag(code, linia=linia)
        if not pallet:
            return False, f"Nie znaleziono palety/Big Baga dla kodu: {code}", None

        if pallet.get('is_blocked'):
            try:
                from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
                if PalletLockManager.reconcile_orphan_transfer_locks() > 0:
                    refreshed = AgroWorkowanieBigBagService.lookup_bigbag(code, linia=linia, auto_reconcile=False)
                    if refreshed and not refreshed.get('is_blocked'):
                        pallet = refreshed
            except Exception:
                pass

        if pallet.get('is_blocked'):
            return False, f"BŁĄD: Paleta {pallet.get('nr_palety')} jest ZABLOKOWANA w magazynie.", None

        stan_dostepny = float(pallet.get('waga') or 0)
        if stan_dostepny <= 0:
            return False, f"Paleta {pallet.get('nr_palety')} ma stan 0 kg (została już zużyta).", None

        waga_do_pobrania = float(ilosc) if ilosc is not None and ilosc > 0 else stan_dostepny
        if waga_do_pobrania > stan_dostepny:
            return False, f"Podana ilość ({waga_do_pobrania:.1f} kg) przekracza dostępny stan Big Baga ({stan_dostepny:.1f} kg).", None

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # Sprawdź czy plan istnieje
            tbl_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"SELECT id, produkt, nazwa_zlecenia FROM {tbl_plan} WHERE id = %s", (plan_id,))
            plan_row = cursor.fetchone()
            if not plan_row:
                return False, f"Zlecenie #{plan_id} nie istnieje.", None

            now = datetime.now()
            table_name = pallet['table_name']
            qty_col = pallet['qty_column']
            pallet_id = pallet['id']
            nr_palety = pallet['nr_palety']
            nazwa_prod = pallet['nazwa']
            nr_partii = pallet['nr_partii']
            dp_str = pallet['data_produkcji']
            dz_str = pallet['data_przydatnosci']
            typ_palety = pallet['typ_palety']
            lokalizacja_zrodlowa = pallet['lokalizacja']

            # 1. Zapis do tabeli agro_workowanie_bigbagi
            cursor.execute("""
                INSERT INTO agro_workowanie_bigbagi (
                    plan_id, paleta_id, nr_palety, nazwa_produktu, waga_kg,
                    nr_partii, data_produkcji, data_przydatnosci, typ_palety,
                    lokalizacja_zrodlowa, stan_magazynowy_przed, autor_login,
                    created_at, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ZUZYTY')
            """, (
                plan_id, pallet_id, nr_palety, nazwa_prod, waga_do_pobrania,
                nr_partii, dp_str, dz_str, typ_palety,
                lokalizacja_zrodlowa, stan_dostepny, worker_login,
                now
            ))
            entry_id = cursor.lastrowid

            # 2. Zdjęcie stanu z magazynu
            nowy_stan = stan_dostepny - waga_do_pobrania
            if nowy_stan <= 0:
                # Jeśli zużyto cały Big Bag -> stan = 0, lokalizacja = PRODUKCJA
                cursor.execute(
                    f"UPDATE {table_name} SET {qty_col} = 0, lokalizacja = 'PRODUKCJA' WHERE id = %s",
                    (pallet_id,)
                )
            else:
                cursor.execute(
                    f"UPDATE {table_name} SET {qty_col} = %s WHERE id = %s",
                    (nowy_stan, pallet_id)
                )

            # 3. Zapis do magazyn_ruch
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(
                    f"""INSERT INTO {table_ruch}
                    (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status,
                     autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, nr_partii)
                    VALUES (%s, %s, 'PRODUKCJA', %s, %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        pallet_id, nazwa_prod, -waga_do_pobrania, nowy_stan,
                        lokalizacja_zrodlowa, worker_login, now, worker_login, now,
                        plan_id, f"Wsad z Big Baga do zlecenia #{plan_id} (Workowanie)", nr_partii
                    )
                )
            except Exception as e_ruch:
                print("Błąd zapisu magazyn_ruch dla Big Baga:", e_ruch)

            # 4. Zapis do palety_historia
            try:
                cursor.execute(
                    """INSERT INTO palety_historia
                    (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                    VALUES (%s, %s, %s, %s, 'WYDANIE_PRODUKCJA', %s, 'Workowanie AGRO', %s, %s, %s)""",
                    (
                        pallet_id, nr_palety, linia.upper(), typ_palety.lower(),
                        lokalizacja_zrodlowa,
                        f"Pobrano wsad {waga_do_pobrania:.1f} kg do zlecenia #{plan_id}",
                        worker_login, now
                    )
                )
            except Exception as e_hist:
                print("Błąd zapisu palety_historia dla Big Baga:", e_hist)

            conn.commit()

            settlement = AgroWorkowanieBigBagService.get_plan_bigbag_settlement(plan_id, linia=linia)
            msg = f"Dodano Big Bag {nr_palety} ({waga_do_pobrania:.1f} kg, partia: {nr_partii}) do zlecenia."
            return True, msg, settlement
        except Exception as e:
            conn.rollback()
            return False, f"Błąd bazy danych podczas dodawania Big Baga: {e}", None
        finally:
            conn.close()

    @staticmethod
    def remove_bigbag_from_plan(
        entry_id: int,
        worker_login: str,
        linia: str = 'AGRO'
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Wycofuje wskanowany Big Bag ze zlecenia i przywraca stan do magazynu."""
        if not entry_id:
            return False, "Brak identyfikatora wpisu Big Baga.", None

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM agro_workowanie_bigbagi WHERE id = %s AND status = 'ZUZYTY'",
                (entry_id,)
            )
            entry = cursor.fetchone()
            if not entry:
                return False, "Nie znaleziono aktywnego wpisu Big Baga lub został już wycofany.", None

            plan_id = entry['plan_id']
            pallet_id = entry['paleta_id']
            waga_kg = float(entry['waga_kg'] or 0)
            lokalizacja_zrodlowa = entry.get('lokalizacja_zrodlowa') or 'Magazyn'
            nr_palety = entry['nr_palety']
            typ_palety = entry.get('typ_palety') or 'Surowiec'

            now = datetime.now()

            # 1. Zmiana statusu w agro_workowanie_bigbagi
            cursor.execute(
                "UPDATE agro_workowanie_bigbagi SET status = 'ZWROCONY' WHERE id = %s",
                (entry_id,)
            )

            # 2. Przywrócenie stanu w tabeli magazynowej (jeśli paleta istnieje)
            if pallet_id:
                if typ_palety == 'Wyrób Gotowy':
                    tbl_name = get_table_name('magazyn_palety', linia)
                    qty_col = 'waga_netto'
                else:
                    tbl_name = get_table_name('magazyn_surowce', linia)
                    qty_col = 'stan_magazynowy'

                try:
                    cursor.execute(f"SELECT {qty_col}, lokalizacja FROM {tbl_name} WHERE id = %s", (pallet_id,))
                    cur_row = cursor.fetchone()
                    if cur_row:
                        curr_qty = float(cur_row.get(qty_col) or 0)
                        nowa_waga = curr_qty + waga_kg
                        # Jeśli paleta miała lokalizację PRODUKCJA, przywróć lokalizację źródłową
                        curr_loc = cur_row.get('lokalizacja') or ''
                        nowa_lok = lokalizacja_zrodlowa if curr_loc in ('PRODUKCJA', 'PRODUKCJA_WORKOWANIE', '') else curr_loc
                        cursor.execute(
                            f"UPDATE {tbl_name} SET {qty_col} = %s, lokalizacja = %s WHERE id = %s",
                            (nowa_waga, nowa_lok, pallet_id)
                        )
                except Exception as e_stock:
                    print(f"Błąd przywracania stanu Big Baga w {tbl_name}: {e_stock}")

            # 3. Zapis ruchu ZWROT do magazyn_ruch
            table_ruch = get_table_name('magazyn_ruch', linia)
            try:
                cursor.execute(
                    f"""INSERT INTO {table_ruch}
                    (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, lokalizacja, status,
                     autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz)
                    VALUES (%s, %s, 'ZWROT', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s)""",
                    (
                        pallet_id, entry['nazwa_produktu'], waga_kg,
                        lokalizacja_zrodlowa, worker_login, now, worker_login, now,
                        plan_id, f"Wycofanie Big Baga {nr_palety} ze zlecenia #{plan_id}"
                    )
                )
            except Exception as e_ruch:
                print("Błąd zapisu zwrotu w magazyn_ruch:", e_ruch)

            # 4. Zapis do palety_historia
            try:
                cursor.execute(
                    """INSERT INTO palety_historia
                    (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                    VALUES (%s, %s, %s, %s, 'ZWROT_Z_PRODUKCJI', 'Workowanie AGRO', %s, %s, %s, %s)""",
                    (
                        pallet_id, nr_palety, linia.upper(), typ_palety.lower(),
                        lokalizacja_zrodlowa,
                        f"Wycofano Big Bag ze zlecenia #{plan_id}",
                        worker_login, now
                    )
                )
            except Exception as e_hist:
                print("Błąd zapisu palety_historia dla wycofania Big Baga:", e_hist)

            conn.commit()

            settlement = AgroWorkowanieBigBagService.get_plan_bigbag_settlement(plan_id, linia=linia)
            return True, f"Wycofano Big Bag {nr_palety} ({waga_kg:.1f} kg) i przywrócono stan na magazyn.", settlement
        except Exception as e:
            conn.rollback()
            return False, f"Błąd bazy danych podczas wycofywania Big Baga: {e}", None
        finally:
            conn.close()

    @staticmethod
    def get_plan_bigbag_settlement(plan_id: int, linia: str = 'AGRO') -> Dict[str, Any]:
        """Zwraca listę wskanowanych Big Bagów i pełny bilans wsadu vs spakowane palety."""
        if not plan_id:
            return {
                'items': [],
                'total_bigbag_kg': 0.0,
                'total_packed_kg': 0.0,
                'bilans_kg': 0.0,
                'loss_pct': 0.0,
                'pallets_count': 0,
                'has_bigbags': False
            }

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Pobierz wskanowane Big Bagi
            cursor.execute("""
                SELECT id, paleta_id, nr_palety, nazwa_produktu, waga_kg,
                       nr_partii, data_produkcji, data_przydatnosci, typ_palety,
                       lokalizacja_zrodlowa, autor_login, created_at, status
                FROM agro_workowanie_bigbagi
                WHERE plan_id = %s AND status = 'ZUZYTY'
                ORDER BY id ASC
            """, (plan_id,))
            bigbags = cursor.fetchall()

            for b in bigbags:
                if b.get('created_at') and hasattr(b['created_at'], 'strftime'):
                    b['created_at_fmt'] = b['created_at'].strftime('%H:%M:%S')
                else:
                    b['created_at_fmt'] = str(b.get('created_at') or '')
                b['waga_kg'] = float(b.get('waga_kg') or 0)

            total_bigbag_kg = sum(float(b['waga_kg']) for b in bigbags)

            # 2. Pobierz spakowane palety na workowaniu
            tbl_palety = 'palety_agro' if linia.upper() == 'AGRO' else 'palety_workowanie'
            cursor.execute(f"""
                SELECT id, nr_palety, COALESCE(waga_potwierdzona, waga, 0) as waga
                FROM {tbl_palety}
                WHERE plan_id = %s AND (status IS NULL OR status != 'anulowana')
            """, (plan_id,))
            pallets = cursor.fetchall()

            total_packed_kg = sum(float(p.get('waga') or 0) for p in pallets)
            pallets_count = len(pallets)

            bilans_kg = total_packed_kg - total_bigbag_kg
            loss_pct = round((bilans_kg / total_bigbag_kg * 100), 2) if total_bigbag_kg > 0 else 0.0

            return {
                'items': bigbags,
                'total_bigbag_kg': round(total_bigbag_kg, 1),
                'total_packed_kg': round(total_packed_kg, 1),
                'bilans_kg': round(bilans_kg, 1),
                'loss_pct': loss_pct,
                'pallets_count': pallets_count,
                'has_bigbags': len(bigbags) > 0
            }
        finally:
            conn.close()
