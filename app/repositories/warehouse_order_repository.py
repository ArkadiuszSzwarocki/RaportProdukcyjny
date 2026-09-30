"""
Repozytorium zamówień magazynowych.

Odpowiedzialność: Operacje CRUD na tabeli magazyn_zamowienia.
Brak logiki biznesowej — tylko dostęp do danych.
"""
from datetime import datetime
import json
import re

from app.core.database import get_db_connection, get_table_name


class WarehouseOrderRepository:
    """Warstwa dostępu do danych zamówień magazynowych."""

    @staticmethod
    def create(items, operator_login, komentarz=None):
        """Tworzy nowe zamówienie w bazie."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            items_json = json.dumps(items, ensure_ascii=False)
            cursor.execute(
                """
                INSERT INTO magazyn_zamowienia
                    (items, operator_login, komentarz, status, created_at)
                VALUES (%s, %s, %s, 'NOWE', %s)
                """,
                (items_json, operator_login, komentarz, datetime.now())
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_all(status_filter=None):
        """Pobiera listę zamówień z opcjonalnym filtrem statusu."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if status_filter:
                cursor.execute(
                    "SELECT * FROM magazyn_zamowienia WHERE status = %s ORDER BY created_at DESC",
                    (status_filter,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM magazyn_zamowienia ORDER BY created_at DESC"
                )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_by_id(order_id):
        """Pobiera zamówienie po ID."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_zamowienia WHERE id = %s",
                (order_id,)
            )
            return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def confirm(order_id, magazynier_login):
        """Potwierdza odczytanie zamówienia — zmiana statusu na ZAMKNIETE."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_zamowienia
                SET status = 'ZAMKNIETE',
                    magazynier_login = %s,
                    confirmed_at = %s
                WHERE id = %s AND status = 'NOWE'
                """,
                (magazynier_login, datetime.now(), order_id)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def delete(order_id):
        """Usuwa zamówienie z bazy danych."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM magazyn_zamowienia WHERE id = %s", (order_id,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def get_available_surowce():
        """Pobiera listę surowców wyłącznie ze słownika surowców."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, nazwa FROM slownik_surowcow "
                "WHERE nazwa IS NOT NULL AND TRIM(nazwa) != '' ORDER BY nazwa ASC"
            )
            dict_rows = cursor.fetchall()

            seen_lower = set()
            items = []
            for row in dict_rows:
                name = str(row['nazwa']).strip()
                name_lower = name.lower()
                if name and name_lower != 'brak nazwy' and name_lower not in seen_lower:
                    seen_lower.add(name_lower)
                    items.append({'id': row['id'], 'nazwa': name})

            return items
        finally:
            conn.close()

    @staticmethod
    def _norm_str(value):
        """Normalizuje nazwę surowca do bezpiecznego porównania 1:1."""
        if not value:
            return ''
        text = str(value).strip().lower()
        repl = {
            'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
            'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z', '\ufffd': '?'
        }
        for source, target in repl.items():
            text = text.replace(source, target)
        return re.sub(r'[^a-z0-9?]', '', text)

    @staticmethod
    def _norm_location(value):
        """Normalizuje kod lokalizacji (BF_MS01, BF-MS01 i BF MS01 => BFMS01)."""
        return re.sub(r'[^A-Z0-9]', '', str(value or '').strip().upper())

    @classmethod
    def _is_osip_location(cls, location):
        """Rozpoznaje lokalizacje należące do OSIP bez importowania modułu raportowego."""
        raw = str(location or '').strip().upper()
        normalized = cls._norm_location(raw)
        if not normalized:
            return False
        return bool(
            'OSIP' in raw
            or normalized.startswith('OS')
            or normalized.startswith('BFOS')
            or normalized == 'WTRANZYCIEOSIP'
            or re.fullmatch(r'A\d{2}', normalized)
        )

    @classmethod
    def _is_allowed_central_location(cls, location):
        """Rozpoznaje regały i dozwolone strefy Magazynu Centralnego."""
        raw = str(location or '').strip().upper()
        if not raw:
            return False

        if cls._is_osip_location(raw):
            return False

        normalized = cls._norm_location(raw)
        if normalized.startswith(('OS', 'MZ', 'KO', 'BB', 'LP')):
            return False
        if 'PODŁOGA' in raw or 'PODLOGA' in raw or 'MASZYNA' in raw:
            return False

        # Regały: R010101, RR030602, R-01-01-01 oraz zapis bez prefiksu 010102.
        if re.fullmatch(r'(?:R|RR)?0[1-9]\d{4}', normalized):
            return True
        if re.fullmatch(r'0[1-9]\d{4}', normalized):
            return True

        allowed_buffers = {
            'MP01', 'MPO1', 'BFMP01',
            'BFMS01', 'MS01',
            'PSD', 'PSD01', 'MGW01', 'MGW02',
            'MOP01', 'MO01', 'MDO01', 'MD01', 'MDM01'
        }
        return normalized in allowed_buffers

    @classmethod
    def _is_searchable_location(cls, location):
        """Zwraca True dla magazynu centralnego i regałów z wymaganymi wykluczeniami."""
        raw = str(location or '').strip().upper()
        if not raw:
            return False

        normalized = cls._norm_location(raw)
        if normalized in {'MS01', 'BFMS01'}:
            return False
        if cls._is_osip_location(raw):
            return False

        return cls._is_allowed_central_location(raw)

    @staticmethod
    def _get_reserved_pallet_ids(cursor):
        """Palety przypisane do aktywnej lub już skompletowanej kompletacji nie są ponownie dostępne."""
        try:
            cursor.execute(
                """
                SELECT DISTINCT paleta_id
                FROM magazyn_kompletacja
                WHERE paleta_id > 0
                  AND status IN ('OCZEKUJE', 'SKOMPLETOWANA')
                """
            )
            return {int(row['paleta_id']) for row in cursor.fetchall() if row.get('paleta_id')}
        except Exception:
            # Starsza instalacja bez tabeli kompletacji nie może blokować samego kalkulatora.
            return set()

    @staticmethod
    def _format_fifo_date(row):
        value = row.get('fifo_date') or row.get('created_at')
        if not value:
            return ''
        try:
            return value.strftime('%Y-%m-%d %H:%M')
        except Exception:
            return str(value)

    @classmethod
    def check_stock(cls, surowce_names, linia='AGRO'):
        """Sprawdza zapotrzebowanie w magazynie centralnym i na regałach oraz przesunięcia w toku z MS01/BFMS01.

        Zasady:
        - przeszukiwane są wszystkie rozpoznane lokalizacje Magazynu Centralnego (MP01, regały R...);
        - uwzględniane są aktywne przesunięcia z MS01 / BFMS01 zmierzające do magazynu produkcyjnego;
        - wykluczone są stacjonarne stany na OSIP, MS01 oraz BFMS01;
        - palety zablokowane są raportowane informacyjnie, ale nie pokrywają zapotrzebowania;
        - nazwa surowca jest dopasowywana dokładnie po normalizacji.
        """
        scanned_zones = [
            'Magazyn Centralny i regały (MP01, regały R...)',
            'Przesunięcia w toku z MS01 / BFMS01 do produkcji',
            'Wykluczone: OSIP, stacjonarne MS01 / BFMS01'
        ]
        if not surowce_names:
            return {'stock_data': {}, 'scanned_zones': scanned_zones}

        table_name = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            fallback_query = f"""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       created_at,
                       COALESCE(is_blocked, 0) AS is_blocked
                FROM {table_name}
                WHERE stan_magazynowy > 0
                ORDER BY created_at ASC, id ASC
            """

            try:
                cursor.execute(
                    f"""
                    SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                           COALESCE(data_produkcji, created_at) AS fifo_date,
                           created_at,
                           COALESCE(is_blocked, 0) AS is_blocked,
                           COALESCE(powod_blokady, '') AS powod_blokady
                    FROM {table_name}
                    WHERE stan_magazynowy > 0
                    ORDER BY fifo_date ASC, id ASC
                    """
                )
                db_rows = cursor.fetchall()
            except Exception:
                cursor.execute(fallback_query)
                db_rows = cursor.fetchall()
                for row in db_rows:
                    row['fifo_date'] = row.get('created_at')
                    row['powod_blokady'] = ''

            # Filtr lokalizacji wykonujemy w jednym miejscu, aby obsłużyć także regały
            # typu 010102 / RR030602 i nie złapać przypadkiem np. RAMPA przez LIKE 'R%'.
            searchable_rows = [
                row for row in db_rows
                if cls._is_searchable_location(row.get('lokalizacja'))
            ]

            # Pobierz pozycje w aktywnych przesunięciach z MS01 / BFMS01 w kierunku magazynu produkcyjnego
            incoming_transfers_by_name = {}
            try:
                cursor.execute(
                    """
                    SELECT id, order_ref, supplier, lokalizacja_z, lokalizacja_do, status, created_at, items, linia
                    FROM magazyn_dostawy
                    WHERE status IN ('OCZEKUJE', 'OPEN', 'W_STREFIE_PRZYJEC', 'PUTAWAY_IN_PROGRESS')
                    """
                )
                transfer_orders = cursor.fetchall()
                for ord_row in transfer_orders:
                    raw_items = ord_row.get('items')
                    if not raw_items:
                        continue
                    try:
                        items_list = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                    except Exception:
                        continue
                    if not isinstance(items_list, list):
                        continue

                    ord_src_raw = str(ord_row.get('lokalizacja_z') or '').strip().upper()

                    for it in items_list:
                        if not isinstance(it, dict) or it.get('accepted') or it.get('rejected') or it.get('putaway_confirmed_at'):
                            continue

                        # Sprawdź lokalizację źródłową pozycji lub zlecenia
                        src_spot = str(it.get('sourceSpot') or it.get('originalSpot') or ord_src_raw or '').strip().upper()
                        src_norm = cls._norm_location(src_spot)

                        # Uwzględniamy wyłącznie ruchy idące Z magazynu MS01 / BFMS01 lub dostawy zewnętrznej
                        if src_norm not in {'MS01', 'BFMS01', 'DOSTAWA'} and not src_spot.startswith(('MS', 'BFMS', 'BF_MS')):
                            continue

                        prod_name = str(it.get('productName') or it.get('nazwa') or '').strip()
                        prod_norm = cls._norm_str(prod_name)
                        if not prod_norm:
                            continue

                        raw_qty = it.get('netWeight') or it.get('quantity') or it.get('ilosc') or it.get('unitsPerPallet') or it.get('stan_magazynowy') or 0.0
                        try:
                            qty = float(raw_qty)
                        except (ValueError, TypeError):
                            qty = 0.0

                        if qty <= 0:
                            continue

                        p_nr = str(it.get('nr_palety') or it.get('sourcePalletNo') or f"TRF-{ord_row.get('id', '')[:8]}").strip()
                        p_batch = str(it.get('nr_partii') or '—').strip()
                        trf_ref = ord_row.get('order_ref') or f"#{str(ord_row.get('id', ''))[:8]}"
                        src_label = src_spot if src_spot else 'MS01'

                        trf_pallet = {
                            'id': it.get('sourcePalletId') or it.get('id') or 0,
                            'nr_palety': p_nr,
                            'lokalizacja': f"W PRZESUNIĘCIU ({src_label} ➔ MP01)",
                            'nr_partii': p_batch,
                            'stan_magazynowy': round(qty, 2),
                            'data': cls._format_fifo_date(ord_row),
                            'is_blocked': False,
                            'is_in_transit': True,
                            'powod_blokady': '',
                            'status_label': f"W drodze z {src_label} ({trf_ref})"
                        }

                        if prod_norm not in incoming_transfers_by_name:
                            incoming_transfers_by_name[prod_norm] = []
                        incoming_transfers_by_name[prod_norm].append(trf_pallet)
            except Exception as trf_err:
                print(f"Error checking incoming transfers in check_stock: {trf_err}")

            final_stock = {}
            for requested_name in surowce_names:
                clean_name = str(requested_name or '').strip()
                requested_norm = cls._norm_str(clean_name)

                active_pallets = []
                blocked_pallets = []
                active_total = 0.0
                blocked_total = 0.0
                active_locations = set()
                blocked_locations = set()

                if requested_norm:
                    for row in searchable_rows:
                        if cls._norm_str(row.get('nazwa')) != requested_norm:
                            continue

                        pallet_id = row.get('id')
                        qty = float(row.get('stan_magazynowy') or 0)
                        is_blocked = bool(row.get('is_blocked'))
                        location = str(row.get('lokalizacja') or '').strip().upper() or 'BRAK'
                        pallet = {
                            'id': pallet_id,
                            'nr_palety': row.get('nr_palety') or f"PAL-{pallet_id}",
                            'lokalizacja': location,
                            'nr_partii': row.get('nr_partii') or '—',
                            'stan_magazynowy': round(qty, 2),
                            'data': cls._format_fifo_date(row),
                            'is_blocked': is_blocked,
                            'powod_blokady': str(row.get('powod_blokady') or '').strip(),
                        }

                        if is_blocked:
                            blocked_total += qty
                            blocked_locations.add(location)
                            blocked_pallets.append(pallet)
                        else:
                            active_total += qty
                            active_locations.add(location)
                            active_pallets.append(pallet)

                    # Dołącz przesunięcia w drodze z MS01 / BFMS01
                    in_transit_pallets = incoming_transfers_by_name.get(requested_norm, [])
                    for trf_p in in_transit_pallets:
                        active_total += trf_p['stan_magazynowy']
                        active_locations.add(trf_p['lokalizacja'])
                        active_pallets.append(trf_p)

                # Wiersze z bazy są w kolejności FIFO; rank nadajemy paletom dostępnym.
                for index, pallet in enumerate(active_pallets, start=1):
                    pallet['fifo_rank'] = index
                    if not pallet.get('status_label'):
                        pallet['status_label'] = f"Wydaj #{index} (FIFO)"

                for pallet in blocked_pallets:
                    pallet['fifo_rank'] = None
                    pallet['status_label'] = (
                        f"ZABLOKOWANA ({pallet['powod_blokady']})"
                        if pallet['powod_blokady'] else 'ZABLOKOWANA'
                    )

                final_stock[clean_name] = {
                    'stan_magazynowy_kg': round(active_total, 2),
                    'zablokowane_kg': round(blocked_total, 2),
                    'lokalizacje': sorted(active_locations),
                    'lokalizacje_zablokowane': sorted(blocked_locations),
                    'palety_fifo': active_pallets + blocked_pallets,
                }

            return {
                'stock_data': final_stock,
                'scanned_zones': scanned_zones,
            }
        finally:
            conn.close()
