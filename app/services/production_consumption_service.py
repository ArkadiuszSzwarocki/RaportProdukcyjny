"""
ProductionConsumptionService — obsługa zużywania etykiet/palet na produkcji do 0 kg
oraz archiwizacji do magazyn_archiwum z pełną historią operacji.
"""

from datetime import datetime
from app.db import get_db_connection, get_table_name
from app.services.scanner_service import ScannerService


class ProductionConsumptionService:
    @staticmethod
    def lookup_pallet_for_consumption(code: str, preferred_line: str = 'PSD') -> dict | None:
        """
        Wyszukuje aktywną paletę (surowiec, opakowanie, dodatek, wyrób gotowy)
        na podstawie zeskanowanego kodu QR/kreskowego/SSCC lub identyfikatora.
        """
        if not code:
            return None

        normalized = ScannerService._normalize_scanned_code(code)
        if not normalized:
            normalized = str(code).strip().upper()

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            lines_to_check = ['PSD', 'AGRO']
            if preferred_line and preferred_line.upper() in lines_to_check:
                lines_to_check = [preferred_line.upper()] + [l for l in lines_to_check if l != preferred_line.upper()]

            prefix, item_id = ScannerService._extract_prefixed_id(normalized)
            is_sscc = ScannerService._is_sscc_code(normalized)

            # 1. Sprawdź Surowce
            for linia in lines_to_check:
                tbl = get_table_name('magazyn_surowce', linia)
                query = f"""
                    SELECT id, nr_palety, nazwa as productName, lokalizacja as location, 
                           stan_magazynowy as amount, data_produkcji, data_przydatnosci, nr_partii as batch,
                           'Surowiec' as type, '{linia}' as linia, 'kg' as unit, is_blocked
                    FROM {tbl}
                    WHERE stan_magazynowy > 0 AND (
                        (nr_palety IS NOT NULL AND (UPPER(nr_palety) = %s OR UPPER(nr_palety) LIKE %s))
                        OR id = %s
                    )
                    LIMIT 1
                """
                cursor.execute(query, (normalized, f"%{normalized}%", item_id or -1))
                row = cursor.fetchone()
                if row:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
                    return row

            # 2. Sprawdź Opakowania
            for linia in lines_to_check:
                tbl = get_table_name('magazyn_opakowania', linia)
                query = f"""
                    SELECT id, nr_palety, nazwa as productName, lokalizacja as location, 
                           stan_magazynowy as amount, data_produkcji, data_przydatnosci, nr_partii as batch,
                           'Opakowanie' as type, '{linia}' as linia, 'szt' as unit, is_blocked
                    FROM {tbl}
                    WHERE stan_magazynowy > 0 AND (
                        (nr_palety IS NOT NULL AND (UPPER(nr_palety) = %s OR UPPER(nr_palety) LIKE %s))
                        OR id = %s
                    )
                    LIMIT 1
                """
                cursor.execute(query, (normalized, f"%{normalized}%", item_id or -1))
                row = cursor.fetchone()
                if row:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
                    return row

            # 3. Sprawdź Dodatki
            try:
                cursor.execute("""
                    SELECT id, nr_palety, nazwa as productName, lokalizacja as location, 
                           stan_magazynowy as amount, NULL as data_produkcji, NULL as data_przydatnosci, 
                           NULL as batch, 'Dodatek' as type, 'PSD' as linia, 'kg' as unit, 0 as is_blocked
                    FROM magazyn_dodatki
                    WHERE stan_magazynowy > 0 AND (
                        (nr_palety IS NOT NULL AND (UPPER(nr_palety) = %s OR UPPER(nr_palety) LIKE %s))
                        OR id = %s
                    )
                    LIMIT 1
                """, (normalized, f"%{normalized}%", item_id or -1))
                row = cursor.fetchone()
                if row:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
                    return row
            except Exception:
                pass

            # 4. Sprawdź Wyroby Gotowe (magazyn_palety / magazyn_palety_agro)
            for linia in lines_to_check:
                tbl_pal = get_table_name('magazyn_palety', linia)
                tbl_plan = get_table_name('plan_produkcji', linia)
                query = f"""
                    SELECT m.id, m.nr_palety, 
                           COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Nieznany produkt') as productName,
                           COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as location,
                           m.waga_netto as amount,
                           COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji) as data_produkcji,
                           COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                           COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, '-') as batch,
                           'Wyrób Gotowy' as type, '{linia}' as linia, 'kg' as unit, m.is_blocked
                    FROM {tbl_pal} m
                    LEFT JOIN {tbl_plan} plan ON m.plan_id = plan.id
                    WHERE m.waga_netto > 0 AND (
                        (m.nr_palety IS NOT NULL AND (UPPER(m.nr_palety) = %s OR UPPER(m.nr_palety) LIKE %s))
                        OR m.id = %s
                    )
                    LIMIT 1
                """
                cursor.execute(query, (normalized, f"%{normalized}%", item_id or -1))
                row = cursor.fetchone()
                if row:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                    return row

            return None
        finally:
            conn.close()

    @staticmethod
    def consume_and_archive_pallet(
        pallet_id: int,
        pallet_type: str,
        linia: str = 'PSD',
        worker_login: str = 'Magazynier',
        comment: str = 'Zużycie w produkcji (wydozowano do 0 kg)'
    ) -> tuple[bool, str, dict | None]:
        """
        Zużywa paletę do 0 kg, przenosi do tabeli `magazyn_archiwum`
        oraz rejestruje zdarzenie w `palety_historia`.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Określ tabelę źródłową
            if pallet_type == 'Surowiec':
                table = get_table_name('magazyn_surowce', linia)
                col_qty = 'stan_magazynowy'
                name_col = 'nazwa'
            elif pallet_type == 'Opakowanie':
                table = get_table_name('magazyn_opakowania', linia)
                col_qty = 'stan_magazynowy'
                name_col = 'nazwa'
            elif pallet_type == 'Dodatek':
                table = 'magazyn_dodatki'
                col_qty = 'stan_magazynowy'
                name_col = 'nazwa'
            else:
                table = get_table_name('magazyn_palety', linia)
                col_qty = 'waga_netto'
                name_col = 'produkt'

            # 1. Pobierz aktualne dane palety
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pallet_id,))
            p = cursor.fetchone()
            if not p:
                return False, "Paleta nie została znaleziona lub została już wcześniej zużyta.", None

            last_weight = float(p.get(col_qty) or 0)
            last_location = p.get('lokalizacja') or 'PRODUKCJA'
            pallet_name = p.get('nazwa') or p.get('produkt') or 'Nieznany produkt'
            pallet_batch = p.get('nr_partii') or '-'
            pallet_sscc = p.get('nr_palety') or f"{pallet_type[:3].upper()}-{pallet_id}"
            pallet_line = p.get('linia') or linia

            # 2. Wstaw do magazyn_archiwum
            cursor.execute("""
                INSERT INTO magazyn_archiwum (
                    original_id, nr_palety, nazwa, typ_palety, linia, 
                    nr_partii, waga_ostatnia, lokalizacja_ostatnia, 
                    user_login, komentarz
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                pallet_id,
                pallet_sscc,
                pallet_name,
                pallet_type,
                pallet_line,
                pallet_batch,
                last_weight,
                last_location,
                worker_login,
                comment
            ))
            archive_id = cursor.lastrowid

            # 3. Usuń paletę z aktywnego magazynu
            cursor.execute(f"DELETE FROM {table} WHERE id = %s", (pallet_id,))

            # 4. Zarejestruj ruch w palety_historia
            try:
                cursor.execute("""
                    INSERT INTO palety_historia (
                        paleta_id, linia, typ_palety, akcja, 
                        lokalizacja_zrodlowa, lokalizacja_docelowa, 
                        komentarz, user_login
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    pallet_id,
                    pallet_line,
                    pallet_type.lower(),
                    'ZUZYCIE_PRODUKCJA',
                    last_location,
                    'ZUZYTE_0KG',
                    f"Zużycie palety do 0 kg na produkcji (waga ost.: {last_weight:.1f})",
                    worker_login
                ))
            except Exception as e:
                print("Błąd zapisu historii:", e)

            conn.commit()

            archived_summary = {
                'id': archive_id,
                'original_id': pallet_id,
                'nr_palety': pallet_sscc,
                'nazwa': pallet_name,
                'typ_palety': pallet_type,
                'linia': pallet_line,
                'nr_partii': pallet_batch,
                'waga_ostatnia': last_weight,
                'lokalizacja_ostatnia': last_location,
                'user_login': worker_login,
                'time': datetime.now().strftime('%H:%M:%S'),
                'data_archiwizacji': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'komentarz': comment
            }

            return True, f"Paleta {pallet_sscc} została pomyślnie zużyta do 0 kg i zarchiwizowana.", archived_summary
        except Exception as e:
            conn.rollback()
            return False, f"Błąd bazy danych podczas zużywania palety: {str(e)}", None
        finally:
            conn.close()

    @staticmethod
    def get_daily_consumption_history(worker_login: str = None, limit: int = 100) -> list[dict]:
        """
        Zwraca listę dzisiejszych zużyć palet z tabeli `magazyn_archiwum`.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Pobierz dzisiejsze rekordy zużycia w produkcji
            query = """
                SELECT id, original_id, nr_palety, nazwa, typ_palety, linia, 
                       nr_partii, waga_ostatnia, lokalizacja_ostatnia, 
                       data_archiwizacji, user_login, komentarz
                FROM magazyn_archiwum
                WHERE (komentarz LIKE '%Zużycie w produkcji%' OR komentarz LIKE '%wydozowano do 0 kg%')
                  AND DATE(data_archiwizacji) = CURDATE()
            """
            params = []
            if worker_login and worker_login.lower() not in ('admin', 'masteradmin', 'kierownik', 'zarzad'):
                query += " AND user_login = %s"
                params.append(worker_login)

            query += " ORDER BY id DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            for r in rows:
                if r.get('data_archiwizacji') and hasattr(r['data_archiwizacji'], 'strftime'):
                    r['time'] = r['data_archiwizacji'].strftime('%H:%M:%S')
                    r['date'] = r['data_archiwizacji'].strftime('%Y-%m-%d')
                else:
                    r['time'] = '-'
                    r['date'] = '-'
            return rows
        except Exception as e:
            print("Błąd pobierania historii zużycia:", e)
            return []
        finally:
            conn.close()
