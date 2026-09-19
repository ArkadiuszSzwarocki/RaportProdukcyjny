"""
Repozytorium zamówień magazynowych.

Odpowiedzialność: Operacje CRUD na tabeli magazyn_zamowienia.
Brak logiki biznesowej — tylko dostęp do danych.
"""
from datetime import datetime
import json
from app.core.database import get_db_connection


class WarehouseOrderRepository:
    """Warstwa dostępu do danych zamówień magazynowych."""

    @staticmethod
    def create(items, operator_login, komentarz=None):
        """Tworzy nowe zamówienie w bazie.

        Args:
            items: Lista obiektów (dict) reprezentująca zamówione surowce.
            operator_login: Login operatora składającego zamówienie.
            komentarz: Opcjonalny komentarz do zamówienia.

        Returns:
            int: ID nowo utworzonego zamówienia.
        """
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
        """Pobiera listę zamówień z opcjonalnym filtrem statusu.

        Args:
            status_filter: Opcjonalny filtr ('NOWE', 'ZAMKNIETE').

        Returns:
            list[dict]: Lista zamówień posortowana od najnowszych.
        """
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
        """Pobiera zamówienie po ID.

        Args:
            order_id: ID zamówienia.

        Returns:
            dict | None: Dane zamówienia lub None.
        """
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
        """Potwierdza odczytanie zamówienia — zmiana statusu na ZAMKNIETE.

        Args:
            order_id: ID zamówienia do potwierdzenia.
            magazynier_login: Login magazyniera potwierdzającego.

        Returns:
            int: Liczba zaktualizowanych wierszy (0 jeśli nie znaleziono lub już zamknięte).
        """
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
        """Usuwa zamówienie z bazy danych.

        Args:
            order_id: ID zamówienia do usunięcia.

        Returns:
            int: Liczba usuniętych wierszy.
        """
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
        """Pobiera listę surowców wyłącznie ze słownika surowców (slownik_surowcow).

        Returns:
            list[dict]: Lista surowców (id, nazwa).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, nazwa FROM slownik_surowcow WHERE nazwa IS NOT NULL AND TRIM(nazwa) != '' ORDER BY nazwa ASC"
            )
            dict_rows = cursor.fetchall()

            seen_lower = set()
            items = []
            for r in dict_rows:
                n = str(r['nazwa']).strip()
                nl = n.lower()
                if n and nl != 'brak nazwy' and nl not in seen_lower:
                    seen_lower.add(nl)
                    items.append({'id': r['id'], 'nazwa': n})

            return items
        finally:
            conn.close()

    @staticmethod
    def _norm_str(s):
        if not s:
            return ''
        import re
        s = str(s).strip().lower()
        repl = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z', '\ufffd': '?'}
        for k, v in repl.items():
            s = s.replace(k, v)
        return re.sub(r'[^a-z0-9?]', '', s)

    @staticmethod
    def check_stock(surowce_names, linia='AGRO'):
        """Sprawdza stany magazynowe, lokalizacje, kolejność FIFO i statusy blokad.

        Ograniczenie magazynów do: regałów (R*), MP01 oraz bufora przyjęć (BF_MP01).

        Args:
            surowce_names: Lista nazw surowców do sprawdzenia.
            linia: Nazwa linii ('AGRO' lub 'PSD').

        Returns:
            dict: Słownik zawierający 'stock_data' oraz 'scanned_zones'.
        """
        scanned_zones = [
            'Regały wysokiego składowania (R*)',
            'Magazyn podręczny (MP01)',
            'Bufor przyjęć surowców (BF_MP01)'
        ]
        if not surowce_names:
            return {'stock_data': {}, 'scanned_zones': scanned_zones}

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Pobierz szczegółowe rekordy palet w aktywnych lokalizacjach
            query = """
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       created_at,
                       COALESCE(is_blocked, 0) as is_blocked
                FROM magazyn_surowce
                WHERE stan_magazynowy > 0
                  AND (
                      LOWER(TRIM(COALESCE(lokalizacja, ''))) = 'mp01'
                      OR LOWER(TRIM(COALESCE(lokalizacja, ''))) IN ('bf_mp01', 'bfmp01')
                      OR LOWER(TRIM(COALESCE(lokalizacja, ''))) LIKE 'r%%'
                  )
                ORDER BY created_at ASC, id ASC
            """
            
            try:
                # Próba z powod_blokady i data_produkcji jeśli istnieją
                query_full = """
                    SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                           COALESCE(data_produkcji, created_at) as fifo_date,
                           created_at,
                           COALESCE(is_blocked, 0) as is_blocked,
                           COALESCE(powod_blokady, '') as powod_blokady
                    FROM magazyn_surowce
                    WHERE stan_magazynowy > 0
                      AND (
                          LOWER(TRIM(COALESCE(lokalizacja, ''))) = 'mp01'
                          OR LOWER(TRIM(COALESCE(lokalizacja, ''))) IN ('bf_mp01', 'bfmp01')
                          OR LOWER(TRIM(COALESCE(lokalizacja, ''))) LIKE 'r%%'
                      )
                    ORDER BY fifo_date ASC, id ASC
                """
                cursor.execute(query_full)
                db_rows = cursor.fetchall()
            except Exception:
                cursor.execute(query)
                db_rows = cursor.fetchall()
                for r in db_rows:
                    r['fifo_date'] = r.get('created_at')
                    r['powod_blokady'] = ''
            
            norm_fn = WarehouseOrderRepository._norm_str
            final_stock = {}
            
            for req_name in surowce_names:
                clean_name = str(req_name).strip()
                req_norm = norm_fn(clean_name)
                if not req_norm:
                    final_stock[clean_name] = {
                        'stan_magazynowy_kg': 0.0,
                        'zablokowane_kg': 0.0,
                        'lokalizacje': [],
                        'palety_fifo': []
                    }
                    continue
                    
                matching_pallets = []
                active_total = 0.0
                blocked_total = 0.0
                locations_set = set()

                for r in db_rows:
                    db_name = r.get('nazwa', '')
                    db_norm = norm_fn(db_name)
                    
                    if req_norm == db_norm or (len(req_norm) > 3 and (req_norm in db_norm or db_norm in req_norm)):
                        qty = float(r.get('stan_magazynowy') or 0)
                        is_blk = bool(r.get('is_blocked'))
                        loc = str(r.get('lokalizacja') or '').strip().upper()
                        if loc:
                            locations_set.add(loc)
                            
                        if is_blk:
                            blocked_total += qty
                        else:
                            active_total += qty

                        f_date_str = ''
                        if r.get('fifo_date'):
                            try:
                                f_date_str = r['fifo_date'].strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                f_date_str = str(r['fifo_date'])
                        elif r.get('created_at'):
                            try:
                                f_date_str = r['created_at'].strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                f_date_str = str(r['created_at'])

                        matching_pallets.append({
                            'id': r.get('id'),
                            'nr_palety': r.get('nr_palety') or f"PAL-{r.get('id')}",
                            'lokalizacja': loc or 'BRAK',
                            'nr_partii': r.get('nr_partii') or '—',
                            'stan_magazynowy': round(qty, 2),
                            'data': f_date_str,
                            'is_blocked': is_blk,
                            'powod_blokady': str(r.get('powod_blokady') or '').strip()
                        })

                # Sortowanie FIFO: najpierw aktywne według daty (kolejność wydań), potem zablokowane
                active_pallets = [p for p in matching_pallets if not p['is_blocked']]
                blocked_pallets = [p for p in matching_pallets if p['is_blocked']]

                for idx, p in enumerate(active_pallets, start=1):
                    p['fifo_rank'] = idx
                    p['status_label'] = f"Wydaj #{idx} (FIFO)"

                for p in blocked_pallets:
                    p['fifo_rank'] = None
                    p['status_label'] = f"ZABLOKOWANA ({p['powod_blokady']})" if p['powod_blokady'] else "ZABLOKOWANA"

                sorted_pallets = active_pallets + blocked_pallets

                final_stock[clean_name] = {
                    'stan_magazynowy_kg': round(active_total, 2),
                    'zablokowane_kg': round(blocked_total, 2),
                    'lokalizacje': sorted(list(locations_set)),
                    'palety_fifo': sorted_pallets
                }

            return {
                'stock_data': final_stock,
                'scanned_zones': scanned_zones
            }
        finally:
            conn.close()
