"""
WarehouseHistoryService — centralny serwis historii ruchów magazynowych i produkcyjnych.
Konsoliduje logowanie zdarzeń oraz odpytywanie historii (stacje zasypowe, przesunięcia regałowe,
wydania, zużycia i archiwizacje) dla linii PSD, AGRO oraz widoku ALL.
"""

from datetime import datetime
from app.db import get_db_connection, get_table_name


class WarehouseHistoryService:
    @staticmethod
    def record_movement(
        paleta_id: int | None,
        linia: str,
        typ_palety: str,
        akcja: str,
        lokalizacja_zrodlowa: str | None,
        lokalizacja_docelowa: str | None,
        komentarz: str | None,
        user_login: str | None = 'System',
        nr_palety: str | None = None
    ) -> bool:
        """
        Zapisuje ruch palety/surowca w centralnej tabeli `palety_historia`.
        """
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO palety_historia (
                    paleta_id, nr_palety, linia, typ_palety, akcja, 
                    lokalizacja_zrodlowa, lokalizacja_docelowa, 
                    komentarz, user_login, data_ruchu
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                paleta_id,
                nr_palety,
                (linia or 'PSD').upper(),
                (typ_palety or 'surowiec').lower(),
                (akcja or 'PRZESUNIECIE').upper(),
                lokalizacja_zrodlowa,
                lokalizacja_docelowa,
                komentarz,
                user_login or 'System',
                datetime.now()
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[WarehouseHistoryService] Błąd zapisu ruchu: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def get_unified_station_and_movement_history(
        linia: str = 'ALL',
        data_od: str | None = None,
        data_do: str | None = None,
        surowiec: str | None = None,
        stacja: str | None = None,
        limit: int = 500
    ) -> list[dict]:
        """
        Zwraca skonsolidowaną historię ruchów magazynowych i stacji produkcyjnych
        łącząc dane z tabeli `palety_historia` oraz legacy `magazyn_ruch` / `magazyn_agro_ruch`.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Date and filter parameters
            date_cond_ph = ""
            date_cond_psd = ""
            date_cond_agro = ""
            date_params_ph = []
            date_params_psd = []
            date_params_agro = []

            if data_od:
                date_cond_ph += " AND ph.data_ruchu >= %s"
                date_params_ph.append(f"{data_od} 00:00:00")
                date_cond_psd += " AND r.created_at >= %s"
                date_params_psd.append(f"{data_od} 00:00:00")
                date_cond_agro += " AND r.autor_data >= %s"
                date_params_agro.append(f"{data_od} 00:00:00")

            if data_do:
                date_cond_ph += " AND ph.data_ruchu <= %s"
                date_params_ph.append(f"{data_do} 23:59:59")
                date_cond_psd += " AND r.created_at <= %s"
                date_params_psd.append(f"{data_do} 23:59:59")
                date_cond_agro += " AND r.autor_data <= %s"
                date_params_agro.append(f"{data_do} 23:59:59")

            line_cond_ph = ""
            line_params_ph = []
            if linia and linia != 'ALL':
                line_cond_ph = " AND ph.linia = %s"
                line_params_ph = [linia]

            stacja_cond_ph = ""
            stacja_params_ph = []
            stacja_cond_legacy = ""
            stacja_params_legacy = []

            if stacja:
                stacja_cond_ph = " AND (ph.lokalizacja_docelowa LIKE %s OR ph.lokalizacja_zrodlowa LIKE %s OR ph.komentarz LIKE %s)"
                stacja_params_ph = [f"%{stacja}%", f"%{stacja}%", f"%{stacja}%"]
                stacja_cond_legacy = " AND (r.zbiornik LIKE %s OR r.lokalizacja LIKE %s OR r.komentarz LIKE %s)"
                stacja_params_legacy = [f"%{stacja}%", f"%{stacja}%", f"%{stacja}%"]
            else:
                # No station filter - show all movements
                stacja_cond_ph = ""
                stacja_params_ph = []
                stacja_cond_legacy = ""
                stacja_params_legacy = []

            sur_cond_ph = ""
            sur_params_ph = []
            sur_cond_legacy = ""
            sur_params_legacy = []
            if surowiec:
                sur_pattern = f"%{surowiec}%"
                sur_cond_ph = """ AND (
                    ph.nr_palety LIKE %s OR
                    sur.nazwa LIKE %s OR sur.nr_palety LIKE %s OR
                    sur_agro.nazwa LIKE %s OR sur_agro.nr_palety LIKE %s OR
                    pal.produkt LIKE %s OR pal.nr_palety LIKE %s OR
                    pal_agro.produkt LIKE %s OR pal_agro.nr_palety LIKE %s OR
                    arch.nazwa LIKE %s OR arch.nr_palety LIKE %s OR
                    ph.komentarz LIKE %s
                )"""
                sur_params_ph = [sur_pattern] * 12
                sur_cond_legacy = " AND (r.surowiec_nazwa LIKE %s OR pal.nazwa LIKE %s OR pal.nr_palety LIKE %s OR r.komentarz LIKE %s)"
                sur_params_legacy = [sur_pattern, sur_pattern, sur_pattern, sur_pattern]

            # 1. Fetch from palety_historia using SSCC (nr_palety) first, scoped by domain/table
            query_ph = f"""
                SELECT 
                    ph.id, 
                    ph.paleta_id,
                    ph.linia as linia_ruch,
                    ph.typ_palety,
                    ph.akcja as typ_ruchu,
                    ph.lokalizacja_zrodlowa,
                    ph.lokalizacja_docelowa,
                    ph.komentarz,
                    ph.user_login as autor_login,
                    ph.data_ruchu as created_at,
                    ph.nr_palety as ph_nr_palety,
                    COALESCE(
                        NULLIF(pal_agro.produkt, ''),
                        NULLIF(pal.produkt, ''),
                        NULLIF(sur_agro.nazwa, ''),
                        NULLIF(sur.nazwa, ''),
                        NULLIF(opk.nazwa, ''),
                        NULLIF(dod.nazwa, ''),
                        NULLIF(arch.nazwa, ''),
                        ''
                    ) as surowiec_nazwa,
                    COALESCE(
                        NULLIF(ph.nr_palety, ''),
                        NULLIF(pal_agro.nr_palety, ''),
                        NULLIF(pal.nr_palety, ''),
                        NULLIF(sur_agro.nr_palety, ''),
                        NULLIF(sur.nr_palety, ''),
                        NULLIF(opk.nr_palety, ''),
                        NULLIF(dod.nr_palety, ''),
                        NULLIF(arch.nr_palety, ''),
                        ''
                    ) as nr_palety,
                    COALESCE(pal_agro.waga_netto, pal.waga_netto, sur_agro.stan_magazynowy, sur.stan_magazynowy, arch.waga_ostatnia, 0) as waga_ref
                FROM palety_historia ph
                LEFT JOIN magazyn_palety_agro pal_agro ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = pal_agro.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND ph.paleta_id = pal_agro.id AND ph.typ_palety IN ('wyrob_gotowy', 'wyrób gotowy', 'paleta') AND ph.linia = 'AGRO')
                )
                LEFT JOIN magazyn_palety pal ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = pal.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND ph.paleta_id = pal.id AND ph.typ_palety IN ('wyrob_gotowy', 'wyrób gotowy', 'paleta') AND ph.linia != 'AGRO')
                )
                LEFT JOIN magazyn_agro_surowce sur_agro ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = sur_agro.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND ph.paleta_id = sur_agro.id AND ph.typ_palety = 'surowiec' AND ph.linia = 'AGRO')
                )
                LEFT JOIN magazyn_surowce sur ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = sur.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND ph.paleta_id = sur.id AND ph.typ_palety = 'surowiec' AND ph.linia != 'AGRO')
                )
                LEFT JOIN magazyn_opakowania opk ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = opk.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND ph.paleta_id = opk.id AND ph.typ_palety = 'opakowanie')
                )
                LEFT JOIN magazyn_dodatki dod ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = dod.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND ph.paleta_id = dod.id AND ph.typ_palety = 'dodatek')
                )
                LEFT JOIN magazyn_archiwum arch ON (
                    (ph.nr_palety IS NOT NULL AND ph.nr_palety != '' AND ph.nr_palety = arch.nr_palety)
                    OR (ph.paleta_id IS NOT NULL AND (ph.paleta_id = arch.original_id OR ph.paleta_id = arch.id))
                )
                WHERE 1=1
                  {line_cond_ph}
                  {date_cond_ph}
                  {stacja_cond_ph}
                  {sur_cond_ph}
                ORDER BY ph.id DESC LIMIT {limit}
            """
            cursor.execute(query_ph, tuple(line_params_ph + date_params_ph + stacja_params_ph + sur_params_ph))
            rows_ph = cursor.fetchall()

            # 2. Fetch from legacy magazyn_ruch (PSD)
            rows_psd = []
            if linia in ('ALL', 'PSD'):
                query_psd = f"""
                    SELECT 
                        r.id, 
                        r.surowiec_id as paleta_id,
                        'PSD' as linia_ruch,
                        'surowiec' as typ_palety,
                        r.typ_ruchu, 
                        r.lokalizacja as lokalizacja_zrodlowa,
                        COALESCE(r.zbiornik, r.lokalizacja) as lokalizacja_docelowa,
                        r.komentarz,
                        r.autor_login, 
                        r.created_at as created_at,
                        COALESCE(NULLIF(r.surowiec_nazwa, ''), pal.nazwa, 'Surowiec') as surowiec_nazwa,
                        COALESCE(pal.nr_palety, '') as nr_palety,
                        ABS(COALESCE(r.ilosc, r.ilosc_po, 0)) as waga_ref
                    FROM magazyn_ruch r
                    LEFT JOIN magazyn_surowce pal ON r.surowiec_id = pal.id
                    WHERE r.typ_ruchu IN ('PRODUKCJA', 'PRZESUNIECIE', 'dosypka', 'bufor_zasyp', 'cleaning', 'PRZYJECIE', 'WYDANIE_PRZESUNIECIE', 'KOREKTA', 'INWENTARYZACJA', 'WYDANIE_PRODUKCJA')
                      {stacja_cond_legacy}
                      {date_cond_psd}
                      {sur_cond_legacy}
                    ORDER BY r.id DESC LIMIT {limit}
                """
                cursor.execute(query_psd, tuple(stacja_params_legacy + date_params_psd + sur_params_legacy))
                rows_psd = cursor.fetchall()

            # 3. Fetch from legacy magazyn_agro_ruch (AGRO)
            rows_agro = []
            if linia in ('ALL', 'AGRO'):
                query_agro = f"""
                    SELECT 
                        r.id, 
                        r.surowiec_id as paleta_id,
                        'AGRO' as linia_ruch,
                        'surowiec' as typ_palety,
                        r.typ_ruchu, 
                        r.lokalizacja as lokalizacja_zrodlowa,
                        COALESCE(r.zbiornik, r.lokalizacja) as lokalizacja_docelowa,
                        r.komentarz,
                        r.autor_login, 
                        r.autor_data as created_at,
                        COALESCE(NULLIF(r.surowiec_nazwa, ''), pal.nazwa, 'Surowiec') as surowiec_nazwa,
                        COALESCE(pal.nr_palety, '') as nr_palety,
                        ABS(COALESCE(r.ilosc, r.ilosc_po, 0)) as waga_ref
                    FROM magazyn_agro_ruch r
                    LEFT JOIN magazyn_agro_surowce pal ON r.surowiec_id = pal.id
                    WHERE r.typ_ruchu IN ('PRODUKCJA', 'PRZESUNIECIE', 'dosypka', 'bufor_zasyp', 'cleaning', 'PRZYJECIE', 'WYDANIE_PRZESUNIECIE', 'KOREKTA', 'INWENTARYZACJA', 'WYDANIE_PRODUKCJA')
                      {stacja_cond_legacy}
                      {date_cond_agro}
                      {sur_cond_legacy}
                    ORDER BY r.id DESC LIMIT {limit}
                """
                cursor.execute(query_agro, tuple(stacja_params_legacy + date_params_agro + sur_params_legacy))
                rows_agro = cursor.fetchall()

            all_rows = rows_ph + rows_psd + rows_agro

            # Parse date helper
            def parse_dt(r):
                dt = r.get('created_at')
                if isinstance(dt, datetime):
                    return dt
                if isinstance(dt, str):
                    try: return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                    except Exception: pass
                return datetime.min

            all_rows.sort(key=parse_dt, reverse=True)

            seen = set()
            deduped = []
            for r in all_rows:
                dt = parse_dt(r)
                dt_key = dt.strftime('%Y-%m-%d %H:%M') if dt != datetime.min else '-'
                key = f"{dt_key}_{r.get('paleta_id')}_{r.get('nr_palety')}_{r.get('typ_ruchu')}_{r.get('lokalizacja_docelowa')}_{r.get('autor_login')}"
                if key in seen:
                    continue
                seen.add(key)

                stacja_val = r.get('lokalizacja_docelowa') or r.get('lokalizacja_zrodlowa') or '-'
                nazwa_val = r.get('surowiec_nazwa') or ''
                koment = str(r.get('komentarz') or '')

                # Extract SSCC from comment if missing
                nr_p_val = r.get('nr_palety') or ''
                if not nr_p_val or nr_p_val == '-':
                    if koment:
                        import re
                        m_sscc = re.search(r'\b(SUR\d{8,20}|AGR\d{8,20}|PSD\d{8,20}|\d{18,20})\b', koment)
                        if m_sscc:
                            nr_p_val = m_sscc.group(1)

                # Extract product name from comment when missing or generic
                if not nazwa_val or nazwa_val == '-' or nazwa_val.lower() in ('surowiec', 'produkt nieznany'):
                    if koment:
                        import re
                        m_prod = re.search(r'(?:paletę|paleta|surowiec|surowca|produkt):\s*([^,;->]+)', koment, re.IGNORECASE)
                        if m_prod:
                            nazwa_val = m_prod.group(1).strip()
                        elif ':' in koment:
                            nazwa_val = koment.split(':')[1].split('->')[0].split(',')[0].strip()

                # Extract quantity from comment or fallback to waga_ref
                ilosc_val = float(r.get('waga_ref') or 0.0)
                if koment:
                    import re
                    m_kw = re.search(r'(?:ilość|ilosc|waga ost\.?|waga|stan|przeniesiono|odjęto|odjeto):\s*([\d\.]+)', koment, re.IGNORECASE)
                    if m_kw:
                        try: ilosc_val = float(m_kw.group(1))
                        except Exception: pass
                    else:
                        m_arrow = re.search(r'->\s*([\d\.]+)', koment)
                        if m_arrow:
                            try: ilosc_val = float(m_arrow.group(1))
                            except Exception: pass
                        else:
                            m_kg = re.search(r'([\d\.]+)\s*kg', koment, re.IGNORECASE)
                            if m_kg and ilosc_val == 0.0:
                                try: ilosc_val = float(m_kg.group(1))
                                except Exception: pass

                # Determine station name from comment if station column is empty or generic
                if stacja_val == '-' and koment:
                    import re
                    m_st = re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*|MGW\d*|Workowanie\s+\w+)\b', koment, re.IGNORECASE)
                    if m_st:
                        stacja_val = m_st.group(1).upper()

                # Better station / location description
                if r.get('lokalizacja_zrodlowa') and r.get('lokalizacja_docelowa') and r.get('lokalizacja_zrodlowa') != r.get('lokalizacja_docelowa'):
                    stacja_val = f"{r.get('lokalizacja_zrodlowa')} -> {r.get('lokalizacja_docelowa')}"

                deduped.append({
                    'id': r['id'],
                    'data': dt.strftime('%Y-%m-%d %H:%M') if dt != datetime.min else '-',
                    'linia': r.get('linia_ruch') or 'PSD',
                    'stacja': stacja_val,
                    'nazwa': nazwa_val or '-',
                    'nr_palety': nr_p_val or '-',
                    'ilosc': ilosc_val,
                    'typ': r.get('typ_ruchu') or '-',
                    'user': r.get('autor_login') or '-',
                    'komentarz': koment or '-'
                })

            result_slice = deduped[:limit]

            # Batch lookup for any unresolved SSCC codes to ensure 100% correct product names
            missing_ssccs = [x['nr_palety'] for x in result_slice if x['nr_palety'] and x['nr_palety'] != '-' and (not x['nazwa'] or x['nazwa'] == '-' or x['nazwa'].lower() in ('surowiec', 'produkt nieznany'))]
            if missing_ssccs:
                sscc_product_map = {}
                placeholders = ', '.join(['%s'] * len(missing_ssccs))
                # 1. Check magazyn_palety_agro
                try:
                    cursor.execute(f"SELECT nr_palety, produkt as nazwa, waga_netto as waga FROM magazyn_palety_agro WHERE nr_palety IN ({placeholders})", tuple(missing_ssccs))
                    for m_row in cursor.fetchall():
                        sscc_product_map[m_row['nr_palety']] = (m_row['nazwa'], float(m_row.get('waga') or 0.0))
                except Exception: pass
                # 2. Check magazyn_palety
                rem = [s for s in missing_ssccs if s not in sscc_product_map]
                if rem:
                    try:
                        cursor.execute(f"SELECT nr_palety, produkt as nazwa, waga_netto as waga FROM magazyn_palety WHERE nr_palety IN ({placeholders[:len(rem)*4-2]})", tuple(rem))
                        for m_row in cursor.fetchall():
                            sscc_product_map[m_row['nr_palety']] = (m_row['nazwa'], float(m_row.get('waga') or 0.0))
                    except Exception: pass
                # 3. Check magazyn_agro_surowce
                rem = [s for s in missing_ssccs if s not in sscc_product_map]
                if rem:
                    try:
                        cursor.execute(f"SELECT nr_palety, nazwa, stan_magazynowy as waga FROM magazyn_agro_surowce WHERE nr_palety IN ({placeholders[:len(rem)*4-2]})", tuple(rem))
                        for m_row in cursor.fetchall():
                            sscc_product_map[m_row['nr_palety']] = (m_row['nazwa'], float(m_row.get('waga') or 0.0))
                    except Exception: pass
                # 4. Check magazyn_surowce
                rem = [s for s in missing_ssccs if s not in sscc_product_map]
                if rem:
                    try:
                        cursor.execute(f"SELECT nr_palety, nazwa, stan_magazynowy as waga FROM magazyn_surowce WHERE nr_palety IN ({placeholders[:len(rem)*4-2]})", tuple(rem))
                        for m_row in cursor.fetchall():
                            sscc_product_map[m_row['nr_palety']] = (m_row['nazwa'], float(m_row.get('waga') or 0.0))
                    except Exception: pass
                # 5. Check magazyn_archiwum
                rem = [s for s in missing_ssccs if s not in sscc_product_map]
                if rem:
                    try:
                        cursor.execute(f"SELECT nr_palety, nazwa, waga_ostatnia as waga FROM magazyn_archiwum WHERE nr_palety IN ({placeholders[:len(rem)*4-2]})", tuple(rem))
                        for m_row in cursor.fetchall():
                            sscc_product_map[m_row['nr_palety']] = (m_row['nazwa'], float(m_row.get('waga') or 0.0))
                    except Exception: pass

                # Apply found names
                for item in result_slice:
                    if item['nr_palety'] in sscc_product_map:
                        item['nazwa'] = sscc_product_map[item['nr_palety']][0]
                        if item['ilosc'] == 0.0 and sscc_product_map[item['nr_palety']][1] > 0:
                            item['ilosc'] = sscc_product_map[item['nr_palety']][1]

            return result_slice
        except Exception as e:
            print(f"[WarehouseHistoryService] Błąd pobierania historii: {e}")
            return []
        finally:
            conn.close()
