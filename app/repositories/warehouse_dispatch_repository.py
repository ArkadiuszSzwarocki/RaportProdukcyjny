"""
Repository wydań zewnętrznych na samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Zapis i odczyt załadunków na samochód w tabeli magazyn_wyjazdy_samochodowe.
"""

from app.core.database import get_db_connection
from app.db_tables import resolve_table_name as get_table_name


class WarehouseDispatchRepository:
    """Repozytorium do obsługi wyjazdów i wydań na samochód."""

    def create_dispatch(self, data):
        """Rejestruje nowe wydanie zewnętrzne na samochód.

        Args:
            data (dict): Słownik zawierający nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                         nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, linia.

        Returns:
            int: ID utworzonego rekordu wydania.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO magazyn_wyjazdy_samochodowe (
                        nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                        nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, linia
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    data.get('magazynier'),
                    data.get('linia', 'AGRO')
                ))
                conn.commit()
                return cursor.lastrowid
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_recent_dispatches(self, limit=50, linia=None):
        """Pobiera listę ostatnich wydań zewnętrznych na samochód filtrowaną wg linii.

        Args:
            limit (int): Maksymalna liczba rekordów.
            linia (str, optional): Linia/oddział np. 'OSIP', 'AGRO', 'PSD' lub None dla wszystkich.

        Returns:
            list[dict]: Lista słowników wydań.
        """
        conn = get_db_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                if linia:
                    linia_upper = str(linia).upper()
                    if linia_upper == 'OSIP':
                        query = """
                            SELECT id, nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                                   nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, linia, created_at
                            FROM magazyn_wyjazdy_samochodowe
                            WHERE UPPER(COALESCE(linia, '')) = 'OSIP' 
                               OR (COALESCE(linia, '') = '' AND (UPPER(COALESCE(magazynier, '')) LIKE '%OSIP%' OR UPPER(COALESCE(uwagi, '')) LIKE '%OSIP%'))
                            ORDER BY created_at DESC
                            LIMIT %s
                        """
                        cursor.execute(query, (limit,))
                    else:
                        query = """
                            SELECT id, nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                                   nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, linia, created_at
                            FROM magazyn_wyjazdy_samochodowe
                            WHERE UPPER(COALESCE(linia, '')) != 'OSIP'
                            ORDER BY created_at DESC
                            LIMIT %s
                        """
                        cursor.execute(query, (limit,))
                else:
                    query = """
                        SELECT id, nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                               nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, linia, created_at
                        FROM magazyn_wyjazdy_samochodowe
                        ORDER BY created_at DESC
                        LIMIT %s
                    """
                    cursor.execute(query, (limit,))

                rows = cursor.fetchall()
                return list(rows) if rows else []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def find_pallet_by_code(self, code, preferred_line='AGRO', prefix=None, item_id=None):
        """Wyszukuje aktywną paletę w magazynie (PSD, AGRO, surowce, opakowania, dodatki, wyroby gotowe, OSIP).

        Args:
            code (str): Znormalizowany kod do wyszukania.
            preferred_line (str): Preferowana linia (AGRO / PSD).
            prefix (str, optional): Prefiks typu np. SUR, OPK, DOD, PAL.
            item_id (int, optional): Wyekstrahowane ID liczbowe.

        Returns:
            dict | None: Słownik danych palety lub None.
        """
        if not code:
            return None

        clean = str(code).strip().upper()
        digits = ''.join([c for c in clean if c.isdigit()])
        num_id = item_id if item_id else (int(clean) if clean.isdigit() and len(clean) < 8 else -1)

        queries = [
            # 1. magazyn_palety (Wyroby Gotowe PSD & AGRO w magazynie)
            ("""
                SELECT id, nr_palety, produkt AS nazwa, waga_netto AS stan_magazynowy,
                       lokalizacja, nr_partii, 'Wyrób Gotowy' AS typ, COALESCE(linia, 'PSD') AS linia,
                       'magazyn_palety' AS src_table
                FROM magazyn_palety
                WHERE waga_netto > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 2. magazyn_palety_agro (Wyroby Gotowe AGRO)
            ("""
                SELECT id, nr_palety, produkt AS nazwa, waga_netto AS stan_magazynowy,
                       lokalizacja, nr_partii, 'Wyrób Gotowy' AS typ, 'AGRO' AS linia,
                       'magazyn_palety_agro' AS src_table
                FROM magazyn_palety_agro
                WHERE waga_netto > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 3. palety_workowanie (Wyroby Gotowe PSD w buforze/produkcji)
            ("""
                SELECT pw.id, pw.nr_palety, COALESCE(p.produkt, pw.nr_palety, 'Wyrób Gotowy') AS nazwa,
                       COALESCE(pw.waga_potwierdzona, pw.waga, 0) AS stan_magazynowy,
                       NULL AS lokalizacja, NULL AS nr_partii, 'Wyrób Gotowy' AS typ, 'PSD' AS linia,
                       'palety_workowanie' AS src_table
                FROM palety_workowanie pw
                LEFT JOIN plan_produkcji p ON pw.plan_id = p.id
                WHERE COALESCE(pw.waga_potwierdzona, pw.waga, 0) > 0 AND (
                    UPPER(COALESCE(pw.nr_palety, '')) = %s 
                    OR UPPER(COALESCE(pw.nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(pw.nr_palety, '')) LIKE %s)
                    OR pw.id = %s
                )
                ORDER BY pw.id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 4. palety_agro (Wyroby Gotowe AGRO w buforze/produkcji)
            ("""
                SELECT pw.id, pw.nr_palety, COALESCE(p.produkt, pw.nr_palety, 'Wyrób Gotowy AGRO') AS nazwa,
                       COALESCE(pw.waga_potwierdzona, pw.waga, 0) AS stan_magazynowy,
                       NULL AS lokalizacja, NULL AS nr_partii, 'Wyrób Gotowy' AS typ, 'AGRO' AS linia,
                       'palety_agro' AS src_table
                FROM palety_agro pw
                LEFT JOIN plan_produkcji_agro p ON pw.plan_id = p.id
                WHERE COALESCE(pw.waga_potwierdzona, pw.waga, 0) > 0 AND (
                    UPPER(COALESCE(pw.nr_palety, '')) = %s 
                    OR UPPER(COALESCE(pw.nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(pw.nr_palety, '')) LIKE %s)
                    OR pw.id = %s
                )
                ORDER BY pw.id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 5. magazyn_surowce (Surowce)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Surowiec' AS typ, COALESCE(linia, 'AGRO') AS linia,
                       'magazyn_surowce' AS src_table
                FROM magazyn_surowce
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 6. magazyn_agro_surowce (Surowce AGRO)
            ("""
                SELECT id, CONCAT('SUR-', id) AS nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Surowiec' AS typ, 'AGRO' AS linia,
                       'magazyn_agro_surowce' AS src_table
                FROM magazyn_agro_surowce
                WHERE stan_magazynowy > 0 AND (
                    CONCAT('SUR-', id) = %s 
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, num_id)),

            # 7. magazyn_opakowania (Opakowania)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Opakowanie' AS typ, COALESCE(linia, 'AGRO') AS linia,
                       'magazyn_opakowania' AS src_table
                FROM magazyn_opakowania
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 8. magazyn_agro_opakowania (Opakowania AGRO)
            ("""
                SELECT id, CONCAT('OPK-', id) AS nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Opakowanie' AS typ, 'AGRO' AS linia,
                       'magazyn_agro_opakowania' AS src_table
                FROM magazyn_agro_opakowania
                WHERE stan_magazynowy > 0 AND (
                    CONCAT('OPK-', id) = %s 
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, num_id)),

            # 9. magazyn_dodatki (Dodatki)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Dodatek' AS typ, COALESCE(linia, 'AGRO') AS linia,
                       'magazyn_dodatki' AS src_table
                FROM magazyn_dodatki
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id)),

            # 10. magazyn_osip_items (OSIP)
            ("""
                SELECT id, nr_palety, nazwa, COALESCE(waga, ilosc, 0) AS stan_magazynowy,
                       lokalizacja, dostawca AS nr_partii, 'Wyrób OSIP' AS typ, 'OSIP' AS linia,
                       'magazyn_osip_items' AS src_table
                FROM magazyn_osip_items
                WHERE (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 6 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR id = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, f"%{clean}%", digits, f"%{digits}%", num_id))
        ]

        conn = get_db_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                for sql, params in queries:
                    try:
                        cursor.execute(sql, params)
                        row = cursor.fetchone()
                        if row:
                            return dict(row)
                    except Exception:
                        continue
                return None
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def deduct_pallet_stock(self, pallet_id, typ_palety, linia, ilosc_kg, src_table=None):
        """Zmniejsza stan magazynowy palety lub zeruje go po wydaniu na samochód.

        Args:
            pallet_id (int): ID palety.
            typ_palety (str): Typ palety ('Surowiec', 'Opakowanie', 'Wyrób Gotowy', itp.).
            linia (str): Linia magazynowa ('AGRO', 'PSD').
            ilosc_kg (float): Wydana ilość w kg.
            src_table (str, optional): Nazwa tabeli źródłowej jeśli znana.

        Returns:
            bool: True jeśli stan został zaktualizowany.
        """
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if src_table in ('magazyn_palety', 'magazyn_palety_agro'):
                    cursor.execute(f"""
                        UPDATE {src_table}
                        SET waga_netto = GREATEST(0, waga_netto - %s), is_loaded = 1
                        WHERE id = %s
                    """, (float(ilosc_kg), pallet_id))
                elif src_table in ('palety_workowanie', 'palety_agro'):
                    cursor.execute(f"""
                        UPDATE {src_table}
                        SET waga = GREATEST(0, waga - %s), status = 'wydana'
                        WHERE id = %s
                    """, (float(ilosc_kg), pallet_id))
                elif src_table == 'magazyn_osip_items':
                    cursor.execute("""
                        UPDATE magazyn_osip_items
                        SET ilosc = GREATEST(0, ilosc - %s), waga = GREATEST(0, waga - %s)
                        WHERE id = %s
                    """, (float(ilosc_kg), float(ilosc_kg), pallet_id))
                else:
                    tbl_name = src_table or ('magazyn_opakowania' if typ_palety == 'Opakowanie' else ('magazyn_dodatki' if typ_palety == 'Dodatek' else 'magazyn_surowce'))
                    cursor.execute(f"""
                        UPDATE {tbl_name}
                        SET stan_magazynowy = GREATEST(0, stan_magazynowy - %s)
                        WHERE id = %s
                    """, (float(ilosc_kg), pallet_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
