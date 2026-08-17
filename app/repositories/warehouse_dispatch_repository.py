"""
Repository wydań zewnętrznych na samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Zapis i odczyt załadunków na samochód w tabeli magazyn_wyjazdy_samochodowe.
"""

from app.core.database import get_db_connection


class WarehouseDispatchRepository:
    """Repozytorium do obsługi wyjazdów i wydań na samochód."""

    def create_dispatch(self, data):
        """Rejestruje nowe wydanie zewnętrzne na samochód.

        Args:
            data (dict): Słownik zawierający nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                         nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier.

        Returns:
            int: ID utworzonego rekordu wydania.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO magazyn_wyjazdy_samochodowe (
                        nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                        nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.get('nr_palety', ''),
                    data.get('nazwa_produktu', ''),
                    data.get('typ_palety', 'Surowiec'),
                    float(data.get('ilosc_kg', 0.0)),
                    data.get('nr_rejestracyjny'),
                    data.get('kierowca'),
                    data.get('odbiorca'),
                    data.get('nr_dokumentu_wz'),
                    data.get('uwagi'),
                    data.get('magazynier')
                ))
                conn.commit()
                return cursor.lastrowid
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_recent_dispatches(self, limit=50):
        """Pobiera listę ostatnich wydań zewnętrznych na samochód.

        Args:
            limit (int): Maksymalna liczba rekordów.

        Returns:
            list[dict]: Lista słowników wydań.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                           nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, created_at
                    FROM magazyn_wyjazdy_samochodowe
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
                return list(rows) if rows else []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_available_pallets(self):
        """Pobiera listę dostępnych palet w magazynie głównym do załadunku.

        Returns:
            list[dict]: Lista palet (id, nr_palety, nazwa, stan_magazynowy, lokalizacja).
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nr_palety, surowiec_nazwa AS nazwa, 'Surowiec' AS typ,
                           stan_magazynowy_kg AS stan_magazynowy, lokalizacja, nr_partii
                    FROM palety_magazynowe
                    WHERE (stan_magazynowy_kg > 0 OR stan_magazynowy_kg IS NULL)
                    ORDER BY created_at DESC
                    LIMIT 200
                """)
                rows = cursor.fetchall()
                return list(rows) if rows else []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
