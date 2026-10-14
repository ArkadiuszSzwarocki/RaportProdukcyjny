"""
Repository wydań zewnętrznych na samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Zapis i odczyt załadunków na samochód w tabeli magazyn_wyjazdy_samochodowe.
"""

from app.core.database import get_db_connection
from app.db_tables import resolve_table_name as get_table_name


class WarehouseDispatchRepository:
    """Repozytorium do obsługi wyjazdów i wydań na samochód."""

    def create_dispatch(self, data, external_conn=None):
        """Rejestruje nowe wydanie zewnętrzne na samochód.

        Args:
            data (dict): Słownik zawierający nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                         nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, linia.

        Returns:
            int: ID utworzonego rekordu wydania.
        """
        conn = external_conn or get_db_connection()
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
                if external_conn is None:
                    conn.commit()
                return cursor.lastrowid
        finally:
            if conn and external_conn is None:
                try:
                    conn.close()
                except Exception:
                    pass

    def dispatch_batch(self, entries):
        """Lock stock and atomically record all WZ documents and ledger movements."""
        import math
        from flask import has_request_context
        from app.core.production_permissions import _page_allowed
        from app.repositories.warehouse_movement_ledger_repository import WarehouseMovementLedgerRepository
        stock_columns = {
            'magazyn_palety': 'waga_netto', 'magazyn_palety_agro': 'waga_netto',
            'palety_workowanie': 'COALESCE(waga_potwierdzona, waga, 0)',
            'palety_agro': 'COALESCE(waga_potwierdzona, waga, 0)',
            'magazyn_surowce': 'stan_magazynowy', 'magazyn_agro_surowce': 'stan_magazynowy',
            'magazyn_opakowania': 'stan_magazynowy', 'magazyn_agro_opakowania': 'stan_magazynowy',
            'magazyn_dodatki': 'stan_magazynowy', 'magazyn_osip_items': 'COALESCE(waga, ilosc, 0)',
        }
        if not entries or any(entry.get('src_table') not in stock_columns for entry in entries):
            raise ValueError('Unsupported stock source')
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            seen = set()
            for entry in sorted(entries, key=lambda item: (item['src_table'], int(item['pallet_id']))):
                table, pallet_id = entry['src_table'], int(entry['pallet_id'])
                if (table, pallet_id) in seen:
                    raise ValueError('Duplicate pallet')
                seen.add((table, pallet_id))
                stock = stock_columns[table]
                cursor.execute(f'SELECT *, {stock} AS available_stock FROM {table} WHERE id=%s FOR UPDATE', (pallet_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError('Missing pallet')
                if row.get('is_blocked') or row.get('is_loaded') or str(row.get('status') or '').lower() in {'wydana', 'zablokowana'}:
                    raise ValueError('Unavailable pallet')
                fixed_line = ('OSIP' if table == 'magazyn_osip_items' else 'AGRO' if table in
                              {'magazyn_palety_agro', 'palety_agro', 'magazyn_agro_surowce', 'magazyn_agro_opakowania'} else
                              'PSD' if table == 'palety_workowanie' else None)
                line = str(fixed_line or row.get('linia') or ('PSD' if table == 'magazyn_palety' else 'AGRO')).upper()
                if line not in {'PSD', 'AGRO', 'OSIP'} or line != str(entry['linia']).upper() or (has_request_context() and not _page_allowed(line, 'magazyn', write=True)):
                    raise ValueError('Wrong warehouse')
                if row.get('nr_palety') and str(row['nr_palety']).upper() != str(entry['nr_palety']).upper():
                    raise ValueError('Changed pallet label')
                quantity, available = float(entry['ilosc_kg']), float(row.get('available_stock') or 0)
                if not math.isfinite(quantity) or not math.isfinite(available) or quantity <= 0 or quantity > available:
                    raise ValueError('Insufficient stock')
                batch = str(row.get('nr_partii') or entry.get('batch') or '').strip().upper()
                if entry.get('required_batch') and batch != entry['required_batch']:
                    raise ValueError('Changed batch')
                cursor.execute("SELECT id FROM lab_blokady WHERE pallet_code=%s AND status='BLOKADA_LAB' FOR UPDATE",
                               (str(entry['nr_palety']).upper(),))
                if cursor.fetchall():
                    raise ValueError('LAB hold')
                remaining = available - quantity
                if table in {'palety_workowanie', 'palety_agro'}:
                    cursor.execute(f"UPDATE {table} SET waga=%s, waga_potwierdzona=IF(waga_potwierdzona IS NULL,NULL,%s), status=IF(%s=0,'wydana',status) WHERE id=%s",
                                   (remaining, remaining, remaining, pallet_id))
                elif table in {'magazyn_palety', 'magazyn_palety_agro'}:
                    cursor.execute(f'UPDATE {table} SET waga_netto=%s, is_loaded=IF(%s=0,1,is_loaded) WHERE id=%s',
                                   (remaining, remaining, pallet_id))
                elif table == 'magazyn_osip_items':
                    cursor.execute('UPDATE magazyn_osip_items SET waga=IF(waga IS NULL,NULL,%s), ilosc=GREATEST(0,COALESCE(ilosc,0)-%s) WHERE id=%s',
                                   (remaining, quantity, pallet_id))
                else:
                    cursor.execute(f'UPDATE {table} SET stan_magazynowy=%s WHERE id=%s', (remaining, pallet_id))
                if cursor.rowcount != 1:
                    raise ValueError('Stock update failed')
            ids = []
            for entry in entries:
                dispatch_id = self.create_dispatch(entry, external_conn=conn)
                if not dispatch_id:
                    raise ValueError('WZ insert failed')
                movement_id = WarehouseMovementLedgerRepository.record_movement(
                    movement_type='WZ', pallet_id=entry['pallet_id'], pallet_code=entry['nr_palety'],
                    product_name=entry['nazwa_produktu'], batch_number=entry.get('batch') or '',
                    source_location=f"MAGAZYN_{entry['linia']}",
                    target_location=f"SAMOCHOD_{entry.get('nr_rejestracyjny') or 'WZ'}",
                    quantity=entry['ilosc_kg'], unit='szt' if entry['typ_palety'] == 'Opakowanie' else 'kg',
                    user_login=entry['magazynier'], reference_id=entry.get('nr_dokumentu_wz') or str(dispatch_id),
                    external_conn=conn)
                if not movement_id:
                    raise ValueError('Ledger insert failed')
                ids.append(dispatch_id)
            cursor.close()
            conn.commit()
            return ids
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
        is_pure_digits = clean.isdigit()
        
        # Gdy wyszukujemy po cyfrach, szukamy od konca (suffix)
        match_clean = f"%{clean}" if is_pure_digits else f"%{clean}%"
        match_digits = f"%{digits}"

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
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

            # 2. magazyn_palety_agro (Wyroby Gotowe AGRO)
            ("""
                SELECT id, nr_palety, produkt AS nazwa, waga_netto AS stan_magazynowy,
                       lokalizacja, nr_partii, 'Wyrób Gotowy' AS typ, 'AGRO' AS linia,
                       'magazyn_palety_agro' AS src_table
                FROM magazyn_palety_agro
                WHERE waga_netto > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

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
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(pw.nr_palety, '')) LIKE %s)
                )
                ORDER BY pw.id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

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
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(pw.nr_palety, '')) LIKE %s)
                )
                ORDER BY pw.id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

            # 5. magazyn_surowce (Surowce)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Surowiec' AS typ, COALESCE(linia, 'AGRO') AS linia,
                       'magazyn_surowce' AS src_table
                FROM magazyn_surowce
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

            # 6. magazyn_agro_surowce (Surowce AGRO)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Surowiec' AS typ, 'AGRO' AS linia,
                       'magazyn_agro_surowce' AS src_table
                FROM magazyn_agro_surowce
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR CONCAT('SUR-', id) = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits, clean)),

            # 7. magazyn_opakowania (Opakowania)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Opakowanie' AS typ, COALESCE(linia, 'AGRO') AS linia,
                       'magazyn_opakowania' AS src_table
                FROM magazyn_opakowania
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

            # 8. magazyn_agro_opakowania (Opakowania AGRO)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Opakowanie' AS typ, 'AGRO' AS linia,
                       'magazyn_agro_opakowania' AS src_table
                FROM magazyn_agro_opakowania
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                    OR CONCAT('OPK-', id) = %s
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits, clean)),

            # 9. magazyn_dodatki (Dodatki)
            ("""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Dodatek' AS typ, COALESCE(linia, 'AGRO') AS linia,
                       'magazyn_dodatki' AS src_table
                FROM magazyn_dodatki
                WHERE stan_magazynowy > 0 AND (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

            # 10. magazyn_osip_items (OSIP)
            ("""
                SELECT id, nr_palety, nazwa, COALESCE(waga, ilosc, 0) AS stan_magazynowy,
                       lokalizacja, dostawca AS nr_partii, 'Wyrób OSIP' AS typ, 'OSIP' AS linia,
                       'magazyn_osip_items' AS src_table
                FROM magazyn_osip_items
                WHERE (
                    UPPER(COALESCE(nr_palety, '')) = %s 
                    OR UPPER(COALESCE(nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(nr_palety, '')) LIKE %s)
                )
                ORDER BY id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits)),

            # 11. osip_transfer_items (Transfery OSIP)
            ("""
                SELECT ti.id, ti.nr_palety, ti.product_name AS nazwa, 
                       COALESCE(ti.loaded_qty, ti.requested_qty, 0) AS stan_magazynowy,
                       t.destination_warehouse AS lokalizacja, NULL AS nr_partii,
                       'Surowiec' AS typ, 'OSIP' AS linia,
                       'osip_transfer_items' AS src_table
                FROM osip_transfer_items ti
                JOIN osip_transfers t ON ti.transfer_id = t.id
                WHERE (
                    UPPER(COALESCE(ti.nr_palety, '')) = %s 
                    OR UPPER(COALESCE(ti.nr_palety, '')) LIKE %s 
                    OR (LENGTH(%s) >= 3 AND UPPER(COALESCE(ti.nr_palety, '')) LIKE %s)
                )
                ORDER BY ti.id DESC LIMIT 1
            """, (clean, match_clean, digits, match_digits))
        ]

        conn = get_db_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                matches = []
                for sql, params in queries:
                    try:
                        cursor.execute(sql, params)
                        rows = cursor.fetchall() or []
                        matches.extend(dict(row) for row in rows)
                    except Exception:
                        continue

                if not matches:
                    return None

                # SSCC is a global identifier. Never silently choose one record
                # when the same number appears in more than one warehouse/table.
                exact_matches = [
                    row for row in matches
                    if str(row.get('nr_palety') or '').strip().upper() == clean
                ]
                candidates = exact_matches or matches
                if len(exact_matches) > 1:
                    return {
                        'duplicate_sscc': True,
                        'nr_palety': clean,
                        'matches': exact_matches,
                    }

                preferred = str(preferred_line or '').strip().upper()
                candidates.sort(key=lambda row: (
                    str(row.get('linia') or '').upper() == preferred,
                    bool(row.get('lokalizacja')),
                    int(row.get('id') or 0),
                ), reverse=True)
                return candidates[0]
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
