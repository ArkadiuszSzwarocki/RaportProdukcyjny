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


class ScannerService:

    # ─────────────────────────────────────────────────────────────────────────
    # LOOKUP — znajdź paletę po lokalizacji lub ID
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def lookup_by_location(location_code: str, linia: str = 'Agro') -> dict | None:
        """Zwraca dane palety dla podanego kodu lokalizacji (R030101) lub ID (SUR-42).

        Returns None jeśli nie znaleziono lub palet jest 0.
        """
        location_code = (location_code or '').strip().upper()
        if not location_code:
            return None

        table_surowce = get_table_name('magazyn_surowce', linia)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)

            # Przypadek 1: kod lokalizacji (zaczyna się od R)
            if location_code.startswith('R'):
                cur.execute(
                    f"SELECT id, nazwa, stan_magazynowy, lokalizacja "
                    f"FROM {table_surowce} WHERE UPPER(lokalizacja) = %s AND stan_magazynowy > 0",
                    (location_code,)
                )
                row = cur.fetchone()
                if row:
                    return _normalize_pallet(row)

            # Przypadek 2: ID numeryczne lub SUR-42
            numeric_id = None
            if location_code.startswith('SUR-'):
                try:
                    numeric_id = int(location_code[4:])
                except ValueError:
                    pass
            else:
                try:
                    numeric_id = int(location_code)
                except ValueError:
                    pass

            if numeric_id is not None:
                cur.execute(
                    f"SELECT id, nazwa, stan_magazynowy, lokalizacja "
                    f"FROM {table_surowce} WHERE id = %s AND stan_magazynowy > 0",
                    (numeric_id,)
                )
                row = cur.fetchone()
                if row:
                    return _normalize_pallet(row)

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
    return {
        'id': row['id'],
        'nazwa': row.get('nazwa') or '',
        'stan_magazynowy': float(row.get('stan_magazynowy') or 0),
        'lokalizacja': row.get('lokalizacja') or '',
    }
