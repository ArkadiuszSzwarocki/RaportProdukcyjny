from app.services.warehouse_history.history_indexer import HistoryIndexer

class HistoryQueryService:
    @staticmethod
    def query_all_history_sources(cursor, conn, linia, data_od, data_do, surowiec, stacja, typ_operacji, limit):
        """Query palety_historia, magazyn_ruch, magazyn_agro_ruch, and finished goods confirmation tables."""
        ph_cols = HistoryIndexer.get_table_columns(cursor, 'palety_historia')
        if 'nr_palety' not in ph_cols:
            try:
                cursor.execute("ALTER TABLE palety_historia ADD COLUMN nr_palety VARCHAR(100) DEFAULT NULL")
                conn.commit()
                ph_cols.add('nr_palety')
            except Exception:
                pass

        has_ph_nr_palety = 'nr_palety' in ph_cols
        sur_agro_cols = HistoryIndexer.get_table_columns(cursor, 'magazyn_agro_surowce')
        has_sur_agro_nr = 'nr_palety' in sur_agro_cols

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
            date_cond_psd += " AND COALESCE(r.autor_data, r.created_at) >= %s"
            date_params_psd.append(f"{data_od} 00:00:00")
            date_cond_agro += " AND COALESCE(r.autor_data, NOW()) >= %s"
            date_params_agro.append(f"{data_od} 00:00:00")

        if data_do:
            date_cond_ph += " AND ph.data_ruchu <= %s"
            date_params_ph.append(f"{data_do} 23:59:59")
            date_cond_psd += " AND COALESCE(r.autor_data, r.created_at) <= %s"
            date_params_psd.append(f"{data_do} 23:59:59")
            date_cond_agro += " AND COALESCE(r.autor_data, NOW()) <= %s"
            date_params_agro.append(f"{data_do} 23:59:59")

        line_cond_ph = ""
        line_params_ph = []
        if linia and linia != 'ALL':
            line_cond_ph = " AND UPPER(COALESCE(ph.linia, '')) = %s"
            line_params_ph = [linia.upper()]

        stacja_cond_ph = ""
        stacja_params_ph = []
        stacja_cond_legacy = ""
        stacja_params_legacy = []

        if stacja:
            stacja_cond_ph = " AND (ph.lokalizacja_docelowa LIKE %s OR ph.lokalizacja_zrodlowa LIKE %s OR ph.komentarz LIKE %s)"
            stacja_params_ph = [f"%{stacja}%", f"%{stacja}%", f"%{stacja}%"]
            stacja_cond_legacy = " AND (r.zbiornik LIKE %s OR r.lokalizacja LIKE %s OR r.komentarz LIKE %s)"
            stacja_params_legacy = [f"%{stacja}%", f"%{stacja}%", f"%{stacja}%"]

        sur_cond_ph = ""
        sur_params_ph = []
        sur_cond_legacy = ""
        sur_params_legacy = []

        matched_pids = set()
        matched_ssccs = set()

        if surowiec:
            sur_clean = surowiec.strip()
            matched_ssccs.add(sur_clean)

            tables_to_resolve = [
                ('magazyn_surowce', 'id', 'nazwa', 'nr_palety'),
                ('magazyn_agro_surowce', 'id', 'nazwa', 'nr_palety'),
                ('magazyn_palety', 'id', 'produkt', 'nr_palety'),
                ('magazyn_palety_agro', 'id', 'produkt', 'nr_palety'),
                ('palety_workowanie', 'id', 'produkt', 'nr_palety'),
                ('palety_agro', 'id', 'produkt', 'nr_palety'),
                ('magazyn_opakowania', 'id', 'nazwa', 'nr_palety'),
                ('magazyn_agro_opakowania', 'id', 'nazwa', 'nr_palety'),
                ('magazyn_dodatki', 'id', 'nazwa', 'nr_palety'),
            ]
            for tbl, id_col, name_col, sscc_col in tables_to_resolve:
                try:
                    cursor.execute(f"""
                        SELECT {id_col} as pid, {sscc_col} as sscc 
                        FROM {tbl} 
                        WHERE {sscc_col} = %s OR {name_col} LIKE %s OR CAST({id_col} AS CHAR) = %s
                        LIMIT 100
                    """, (sur_clean, f"%{sur_clean}%", sur_clean))
                    for r in cursor.fetchall() or []:
                        if r.get('pid'):
                            matched_pids.add(int(r['pid']))
                        if r.get('sscc'):
                            matched_ssccs.add(str(r['sscc']).strip())
                except Exception:
                    pass

            try:
                cursor.execute(
                    "SELECT paleta_id, nr_palety FROM palety_historia WHERE nr_palety = %s OR komentarz LIKE %s LIMIT 100",
                    (sur_clean, f"%{sur_clean}%")
                )
                for r in cursor.fetchall() or []:
                    if r.get('paleta_id'):
                        matched_pids.add(int(r['paleta_id']))
                    if r.get('nr_palety'):
                        matched_ssccs.add(str(r['nr_palety']).strip())
            except Exception:
                pass

            ph_clauses = ["ph.komentarz LIKE %s", "ph.typ_palety LIKE %s"]
            sur_params_ph = [f"%{sur_clean}%", f"%{sur_clean}%"]
            if matched_ssccs:
                ph_ph_sscc = ', '.join(['%s'] * len(matched_ssccs))
                ph_clauses.append(f"ph.nr_palety IN ({ph_ph_sscc})")
                sur_params_ph.extend(list(matched_ssccs))
            if matched_pids:
                ph_ph_id = ', '.join(['%s'] * len(matched_pids))
                ph_clauses.append(f"ph.paleta_id IN ({ph_ph_id})")
                sur_params_ph.extend(list(matched_pids))
            sur_cond_ph = f" AND ({' OR '.join(ph_clauses)})"

            legacy_clauses = ["r.surowiec_nazwa LIKE %s", "r.komentarz LIKE %s"]
            sur_params_legacy = [f"%{sur_clean}%", f"%{sur_clean}%"]
            if matched_pids:
                leg_ph_id = ', '.join(['%s'] * len(matched_pids))
                legacy_clauses.append(f"r.surowiec_id IN ({leg_ph_id})")
                sur_params_legacy.extend(list(matched_pids))
            sur_cond_legacy = f" AND ({' OR '.join(legacy_clauses)})"

        type_cond_ph = ""
        type_params_ph = []
        type_cond_legacy = ""
        type_params_legacy = []

        if typ_operacji and typ_operacji != 'ALL':
            t_clean = typ_operacji.upper().strip()
            if t_clean in ('UTWORZENIE', 'UTWORZENIE_PALETY'):
                type_cond_ph = " AND (UPPER(ph.akcja) IN ('UTWORZENIE', 'UTWORZENIE_PALETY', 'UTWORZ') OR ph.akcja LIKE '%UTWORZ%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) IN ('UTWORZENIE', 'UTWORZENIE_PALETY', 'UTWORZ') OR r.typ_ruchu LIKE '%UTWORZ%')"
            elif t_clean == 'PRZYJECIE':
                type_cond_ph = " AND (UPPER(ph.akcja) IN ('PRZYJECIE', 'PRZYJĘCIE', 'PW', 'PZ') OR ph.akcja LIKE '%PRZYJ%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) IN ('PRZYJECIE', 'PRZYJĘCIE', 'PW', 'PZ') OR r.typ_ruchu LIKE '%PRZYJ%')"
            elif t_clean == 'WYDANIE':
                type_cond_ph = " AND (UPPER(ph.akcja) IN ('WYDANIE', 'PROD', 'RW', 'WZ') OR ph.akcja LIKE '%WYDA%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) IN ('WYDANIE', 'PROD', 'RW', 'WZ') OR r.typ_ruchu LIKE '%WYDA%')"
            elif t_clean == 'PODZIAL':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%PODZIAL%' OR UPPER(ph.akcja) LIKE '%PODZIAŁ%' OR ph.komentarz LIKE '%podział%' OR ph.komentarz LIKE '%podzial%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%PODZIAL%' OR UPPER(r.typ_ruchu) LIKE '%PODZIAŁ%' OR r.komentarz LIKE '%podział%' OR r.komentarz LIKE '%podzial%')"
            elif t_clean == 'PRZESUNIECIE':
                type_cond_ph = " AND (UPPER(ph.akcja) IN ('PRZESUNIECIE', 'PRZESUNIĘCIE', 'TRANSFER', 'RELOKACJA', 'RUCH', 'MM') OR ph.akcja LIKE '%PRZESUN%') AND ph.akcja NOT LIKE '%PODZIAL%'"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) IN ('PRZESUNIECIE', 'PRZESUNIĘCIE', 'TRANSFER', 'RELOKACJA', 'RUCH', 'MM') OR r.typ_ruchu LIKE '%PRZESUN%') AND r.typ_ruchu NOT LIKE '%PODZIAL%'"
            elif t_clean == 'ZASYP':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%ZASYP%' OR UPPER(ph.akcja) LIKE '%BUFOR%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%ZASYP%' OR UPPER(r.typ_ruchu) LIKE '%BUFOR%')"
            elif t_clean == 'DOSYPKA':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%DOSYP%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%DOSYP%')"
            elif t_clean == 'CZYSZCZENIE':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%CZYSZCZ%' OR UPPER(ph.akcja) LIKE '%CLEAN%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%CZYSZCZ%' OR UPPER(r.typ_ruchu) LIKE '%CLEAN%')"
            elif t_clean == 'USUNIECIE':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%USUN%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%USUN%')"
            elif t_clean == 'INWENTARYZACJA':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%INWENT%' OR UPPER(ph.akcja) LIKE '%KOREKT%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%INWENT%' OR UPPER(r.typ_ruchu) LIKE '%KOREKT%')"
            elif t_clean == 'OPAKOWANIE':
                type_cond_ph = " AND (UPPER(ph.akcja) LIKE '%OPAKOW%' OR UPPER(ph.akcja) LIKE '%TYP%')"
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) LIKE '%OPAKOW%' OR UPPER(r.typ_ruchu) LIKE '%TYP%')"
            else:
                type_cond_ph = " AND (UPPER(ph.akcja) = %s)"
                type_params_ph = [t_clean]
                type_cond_legacy = " AND (UPPER(r.typ_ruchu) = %s)"
                type_params_legacy = [t_clean]

        # 1. Query palety_historia
        nr_pal_select = "ph.nr_palety" if has_ph_nr_palety else "'' as nr_palety"
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
                '' as surowiec_nazwa,
                {nr_pal_select},
                0.0 as waga_ref
            FROM palety_historia ph
            WHERE 1=1
              {line_cond_ph}
              {date_cond_ph}
              {stacja_cond_ph}
              {type_cond_ph}
              {sur_cond_ph}
            ORDER BY ph.data_ruchu DESC LIMIT {limit}
        """
        cursor.execute(query_ph, tuple(line_params_ph + date_params_ph + stacja_params_ph + type_params_ph + sur_params_ph))
        rows_ph = cursor.fetchall() or []

        # 2. Query legacy magazyn_ruch (PSD)
        rows_psd = []
        if linia in ('ALL', 'PSD'):
            try:
                query_psd = f"""
                    SELECT 
                        r.id, 
                        r.surowiec_id as paleta_id,
                        'PSD' as linia_ruch,
                        'surowiec' as typ_palety,
                        r.typ_ruchu, 
                        NULL as lokalizacja_zrodlowa,
                        COALESCE(r.zbiornik, r.lokalizacja) as lokalizacja_docelowa,
                        r.komentarz,
                        r.autor_login, 
                        COALESCE(r.autor_data, r.created_at) as created_at,
                        COALESCE(NULLIF(r.surowiec_nazwa, ''), 'Surowiec') as surowiec_nazwa,
                        '' as nr_palety,
                        ABS(COALESCE(r.ilosc, r.ilosc_po, 0)) as waga_ref
                    FROM magazyn_ruch r
                    WHERE 1=1
                      {stacja_cond_legacy}
                      {date_cond_psd}
                      {type_cond_legacy}
                      {sur_cond_legacy}
                    ORDER BY r.id DESC LIMIT {limit}
                """
                cursor.execute(query_psd, tuple(stacja_params_legacy + date_params_psd + type_params_legacy + sur_params_legacy))
                rows_psd = cursor.fetchall() or []
            except Exception as e_psd:
                print(f"[WarehouseHistoryService] Query psd error: {e_psd}")

        # 3. Query legacy magazyn_agro_ruch (AGRO)
        rows_agro = []
        if linia in ('ALL', 'AGRO'):
            try:
                query_agro = f"""
                    SELECT 
                        r.id, 
                        r.surowiec_id as paleta_id,
                        'AGRO' as linia_ruch,
                        'surowiec' as typ_palety,
                        r.typ_ruchu, 
                        NULL as lokalizacja_zrodlowa,
                        COALESCE(r.zbiornik, r.lokalizacja) as lokalizacja_docelowa,
                        r.komentarz,
                        r.autor_login, 
                        COALESCE(r.autor_data, NOW()) as created_at,
                        COALESCE(NULLIF(r.surowiec_nazwa, ''), 'Surowiec AGRO') as surowiec_nazwa,
                        '' as nr_palety,
                        ABS(COALESCE(r.ilosc, r.ilosc_po, 0)) as waga_ref
                    FROM magazyn_agro_ruch r
                    WHERE 1=1
                      {stacja_cond_legacy}
                      {date_cond_agro}
                      {type_cond_legacy}
                      {sur_cond_legacy}
                    ORDER BY r.id DESC LIMIT {limit}
                """
                cursor.execute(query_agro, tuple(stacja_params_legacy + date_params_agro + type_params_legacy + sur_params_legacy))
                rows_agro = cursor.fetchall() or []
            except Exception as e_agro:
                print(f"[WarehouseHistoryService] Query agro error: {e_agro}")

        # 4. Query finished goods confirmations from magazyn_palety (PSD) and magazyn_palety_agro (AGRO)
        rows_conf = []
        if typ_operacji in (None, '', 'ALL', 'PRZYJECIE'):
            date_cond_conf_psd = ""
            date_params_conf_psd = []
            date_cond_conf_agro = ""
            date_params_conf_agro = []
            if data_od:
                date_cond_conf_psd += " AND mp.data_potwierdzenia >= %s"
                date_params_conf_psd.append(f"{data_od} 00:00:00")
                date_cond_conf_agro += " AND mpa.data_potwierdzenia >= %s"
                date_params_conf_agro.append(f"{data_od} 00:00:00")
            if data_do:
                date_cond_conf_psd += " AND mp.data_potwierdzenia <= %s"
                date_params_conf_psd.append(f"{data_do} 23:59:59")
                date_cond_conf_agro += " AND mpa.data_potwierdzenia <= %s"
                date_params_conf_agro.append(f"{data_do} 23:59:59")

            stacja_cond_conf = ""
            stacja_params_conf = []
            if stacja:
                stacja_cond_conf = " AND (lokalizacja LIKE %s)"
                stacja_params_conf = [f"%{stacja}%"]

            sur_cond_conf = ""
            sur_params_conf = []
            if surowiec:
                conf_clauses = ["produkt LIKE %s", "nr_palety LIKE %s"]
                sur_params_conf = [f"%{sur_clean}%", f"%{sur_clean}%"]
                if matched_ssccs:
                    conf_ph_sscc = ', '.join(['%s'] * len(matched_ssccs))
                    conf_clauses.append(f"nr_palety IN ({conf_ph_sscc})")
                    sur_params_conf.extend(list(matched_ssccs))
                if matched_pids:
                    conf_ph_id = ', '.join(['%s'] * len(matched_pids))
                    conf_clauses.append(f"id IN ({conf_ph_id})")
                    sur_params_conf.extend(list(matched_pids))
                sur_cond_conf = f" AND ({' OR '.join(conf_clauses)})"

            ph_known_pallet_nrs = {str(r.get('nr_palety') or '').strip().upper() for r in rows_ph if r.get('nr_palety')}
            ph_known_pallet_ids = {int(r['paleta_id']) for r in rows_ph if str(r.get('paleta_id') or '').isdigit()}

            if linia in ('ALL', 'PSD'):
                try:
                    q_conf_psd = f"""
                        SELECT 
                            mp.id, 
                            mp.id as paleta_id,
                            mp.paleta_workowanie_id,
                            'PSD' as linia_ruch,
                            'wyrob_gotowy' as typ_palety,
                            'PRZYJECIE' as typ_ruchu, 
                            'Produkcja PSD' as lokalizacja_zrodlowa,
                            COALESCE(NULLIF(mp.lokalizacja, ''), 'OCZEKUJĄCE') as lokalizacja_docelowa,
                            CONCAT('Rejestracja wyrobu (oczekuje na przyjęcie)', IF(mp.lokalizacja IS NOT NULL AND mp.lokalizacja != '' AND mp.lokalizacja != 'OCZEKUJĄCE', CONCAT(' -> ', mp.lokalizacja), '')) as komentarz,
                            COALESCE(mp.user_login, 'System') as autor_login, 
                            mp.data_potwierdzenia as created_at,
                            COALESCE(mp.produkt, 'Wyrób gotowy') as surowiec_nazwa,
                            COALESCE(mp.nr_palety, '') as nr_palety,
                            ABS(COALESCE(mp.waga_netto, 0.0)) as waga_ref
                        FROM magazyn_palety mp
                        WHERE mp.data_potwierdzenia IS NOT NULL
                          {date_cond_conf_psd}
                          {stacja_cond_conf.replace('lokalizacja', 'mp.lokalizacja')}
                          {sur_cond_conf.replace('produkt', 'mp.produkt').replace('nr_palety', 'mp.nr_palety')}
                        ORDER BY mp.id DESC LIMIT {limit}
                    """
                    cursor.execute(q_conf_psd, tuple(date_params_conf_psd + stacja_params_conf + sur_params_conf))
                    for row in cursor.fetchall() or []:
                        r_nr = str(row.get('nr_palety') or '').strip().upper()
                        r_pid = row.get('paleta_id')
                        r_pwid = row.get('paleta_workowanie_id')
                        if r_nr and r_nr in ph_known_pallet_nrs:
                            continue
                        if r_pid and r_pid in ph_known_pallet_ids:
                            continue
                        if r_pwid and r_pwid in ph_known_pallet_ids:
                            continue
                        rows_conf.append(row)
                except Exception as e_cp:
                    print(f"[WarehouseHistoryService] Query conf psd error: {e_cp}")

            if linia in ('ALL', 'AGRO'):
                try:
                    q_conf_agro = f"""
                        SELECT 
                            mpa.id, 
                            mpa.id as paleta_id,
                            mpa.paleta_workowanie_id,
                            'AGRO' as linia_ruch,
                            'wyrob_gotowy' as typ_palety,
                            'PRZYJECIE' as typ_ruchu, 
                            'Produkcja AGRO' as lokalizacja_zrodlowa,
                            COALESCE(NULLIF(mpa.lokalizacja, ''), 'OCZEKUJĄCE') as lokalizacja_docelowa,
                            CONCAT('Rejestracja wyrobu (oczekuje na przyjęcie)', IF(mpa.lokalizacja IS NOT NULL AND mpa.lokalizacja != '' AND mpa.lokalizacja != 'OCZEKUJĄCE', CONCAT(' -> ', mpa.lokalizacja), '')) as komentarz,
                            COALESCE(mpa.user_login, 'System') as autor_login, 
                            mpa.data_potwierdzenia as created_at,
                            COALESCE(mpa.produkt, 'Wyrób gotowy') as surowiec_nazwa,
                            COALESCE(mpa.nr_palety, '') as nr_palety,
                            ABS(COALESCE(mpa.waga_netto, 0.0)) as waga_ref
                        FROM magazyn_palety_agro mpa
                        WHERE mpa.data_potwierdzenia IS NOT NULL
                          {date_cond_conf_agro}
                          {stacja_cond_conf.replace('lokalizacja', 'mpa.lokalizacja')}
                          {sur_cond_conf.replace('produkt', 'mpa.produkt').replace('nr_palety', 'mpa.nr_palety')}
                        ORDER BY mpa.id DESC LIMIT {limit}
                    """
                    cursor.execute(q_conf_agro, tuple(date_params_conf_agro + stacja_params_conf + sur_params_conf))
                    for row in cursor.fetchall() or []:
                        r_nr = str(row.get('nr_palety') or '').strip().upper()
                        r_pid = row.get('paleta_id')
                        r_pwid = row.get('paleta_workowanie_id')
                        if r_nr and r_nr in ph_known_pallet_nrs:
                            continue
                        if r_pid and r_pid in ph_known_pallet_ids:
                            continue
                        if r_pwid and r_pwid in ph_known_pallet_ids:
                            continue
                        rows_conf.append(row)
                except Exception as e_ca:
                    print(f"[WarehouseHistoryService] Query conf agro error: {e_ca}")

        # 5. Query finished goods creation from palety_workowanie (PSD) and palety_agro (AGRO)
        rows_creation = []
        if typ_operacji in (None, '', 'ALL', 'UTWORZENIE', 'UTWORZENIE_PALETY'):
            date_cond_prod_psd = ""
            date_params_prod_psd = []
            date_cond_prod_agro = ""
            date_params_prod_agro = []
            if data_od:
                date_cond_prod_psd += " AND pw.data_dodania >= %s"
                date_params_prod_psd.append(f"{data_od} 00:00:00")
                date_cond_prod_agro += " AND pa.data_dodania >= %s"
                date_params_prod_agro.append(f"{data_od} 00:00:00")
            if data_do:
                date_cond_prod_psd += " AND pw.data_dodania <= %s"
                date_params_prod_psd.append(f"{data_do} 23:59:59")
                date_cond_prod_agro += " AND pa.data_dodania <= %s"
                date_params_prod_agro.append(f"{data_do} 23:59:59")

            sur_cond_prod_psd = ""
            sur_params_prod_psd = []
            sur_cond_prod_agro = ""
            sur_params_prod_agro = []
            if surowiec:
                cl_psd = ["pp.produkt LIKE %s", "pw.nr_palety LIKE %s"]
                sur_params_prod_psd = [f"%{sur_clean}%", f"%{sur_clean}%"]
                cl_agro = ["ppa.produkt LIKE %s", "pa.nr_palety LIKE %s"]
                sur_params_prod_agro = [f"%{sur_clean}%", f"%{sur_clean}%"]
                if matched_ssccs:
                    ph_sscc_c = ', '.join(['%s'] * len(matched_ssccs))
                    cl_psd.append(f"pw.nr_palety IN ({ph_sscc_c})")
                    sur_params_prod_psd.extend(list(matched_ssccs))
                    cl_agro.append(f"pa.nr_palety IN ({ph_sscc_c})")
                    sur_params_prod_agro.extend(list(matched_ssccs))
                if matched_pids:
                    ph_pid_c = ', '.join(['%s'] * len(matched_pids))
                    cl_psd.append(f"pw.id IN ({ph_pid_c})")
                    sur_params_prod_psd.extend(list(matched_pids))
                    cl_agro.append(f"pa.id IN ({ph_pid_c})")
                    sur_params_prod_agro.extend(list(matched_pids))
                sur_cond_prod_psd = f" AND ({' OR '.join(cl_psd)})"
                sur_cond_prod_agro = f" AND ({' OR '.join(cl_agro)})"

            ph_creation_nrs = {
                str(r.get('nr_palety') or '').strip().upper() 
                for r in rows_ph 
                if r.get('nr_palety') and any(k in str(r.get('typ_ruchu') or '').upper() for k in ('UTWORZ',))
            }
            ph_creation_ids = {
                int(r['paleta_id']) 
                for r in rows_ph 
                if str(r.get('paleta_id') or '').isdigit() and any(k in str(r.get('typ_ruchu') or '').upper() for k in ('UTWORZ',))
            }

            if linia in ('ALL', 'PSD'):
                try:
                    q_prod_psd = f"""
                        SELECT 
                            pw.id, 
                            pw.id as paleta_id,
                            'PSD' as linia_ruch,
                            'wyrob_gotowy' as typ_palety,
                            'UTWORZENIE' as typ_ruchu, 
                            'Linia PSD' as lokalizacja_zrodlowa,
                            'OCZEKUJĄCE' as lokalizacja_docelowa,
                            CONCAT('Utworzono paletę: ', COALESCE(pp.produkt, 'Wyrób gotowy PSD'), ', waga: ', ROUND(COALESCE(NULLIF(pw.waga_potwierdzona, 0), pw.waga, 0), 1), ' kg', IF(pw.plan_id IS NOT NULL, CONCAT(' (Zlecenie #', pw.plan_id, ')'), '')) as komentarz,
                            COALESCE(pw.dodal_login, 'System') as autor_login, 
                            pw.data_dodania as created_at,
                            COALESCE(pp.produkt, 'Wyrób gotowy PSD') as surowiec_nazwa,
                            COALESCE(pw.nr_palety, '') as nr_palety,
                            ABS(COALESCE(NULLIF(pw.waga_potwierdzona, 0), pw.waga, 0.0)) as waga_ref
                        FROM palety_workowanie pw
                        LEFT JOIN plan_produkcji pp ON pw.plan_id = pp.id
                        WHERE pw.data_dodania IS NOT NULL
                          {date_cond_prod_psd}
                          {sur_cond_prod_psd}
                        ORDER BY pw.id DESC LIMIT {limit}
                    """
                    cursor.execute(q_prod_psd, tuple(date_params_prod_psd + sur_params_prod_psd))
                    for row in cursor.fetchall() or []:
                        r_nr = str(row.get('nr_palety') or '').strip().upper()
                        r_pid = row.get('paleta_id')
                        if r_nr and r_nr in ph_creation_nrs:
                            continue
                        if r_pid and r_pid in ph_creation_ids:
                            continue
                        rows_creation.append(row)
                except Exception as e_pr_psd:
                    print(f"[WarehouseHistoryService] Query prod psd error: {e_pr_psd}")

            if linia in ('ALL', 'AGRO'):
                try:
                    q_prod_agro = f"""
                        SELECT 
                            pa.id, 
                            pa.id as paleta_id,
                            'AGRO' as linia_ruch,
                            'wyrob_gotowy' as typ_palety,
                            'UTWORZENIE' as typ_ruchu, 
                            'Linia AGRO' as lokalizacja_zrodlowa,
                            'OCZEKUJĄCE' as lokalizacja_docelowa,
                            CONCAT('Utworzono paletę: ', COALESCE(ppa.produkt, 'Wyrób gotowy AGRO'), ', waga: ', ROUND(COALESCE(NULLIF(pa.waga_potwierdzona, 0), pa.waga, 0), 1), ' kg', IF(pa.plan_id IS NOT NULL, CONCAT(' (Zlecenie #', pa.plan_id, ')'), '')) as komentarz,
                            COALESCE(pa.dodal_login, 'System') as autor_login, 
                            pa.data_dodania as created_at,
                            COALESCE(ppa.produkt, 'Wyrób gotowy AGRO') as surowiec_nazwa,
                            COALESCE(pa.nr_palety, '') as nr_palety,
                            ABS(COALESCE(NULLIF(pa.waga_potwierdzona, 0), pa.waga, 0.0)) as waga_ref
                        FROM palety_agro pa
                        LEFT JOIN plan_produkcji_agro ppa ON pa.plan_id = ppa.id
                        WHERE pa.data_dodania IS NOT NULL
                          {date_cond_prod_agro}
                          {sur_cond_prod_agro}
                        ORDER BY pa.id DESC LIMIT {limit}
                    """
                    cursor.execute(q_prod_agro, tuple(date_params_prod_agro + sur_params_prod_agro))
                    for row in cursor.fetchall() or []:
                        r_nr = str(row.get('nr_palety') or '').strip().upper()
                        r_pid = row.get('paleta_id')
                        if r_nr and r_nr in ph_creation_nrs:
                            continue
                        if r_pid and r_pid in ph_creation_ids:
                            continue
                        rows_creation.append(row)
                except Exception as e_pr_agro:
                    print(f"[WarehouseHistoryService] Query prod agro error: {e_pr_agro}")

        return rows_ph + rows_psd + rows_agro + rows_conf + rows_creation
