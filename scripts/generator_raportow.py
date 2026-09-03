import pandas as pd
import os
from pathlib import Path
from datetime import datetime
from app.db import get_db_connection, get_table_name
import logging

logger = logging.getLogger(__name__)

def generuj_paczke_raportow(data_raportu, uwagi_lidera, lider_name='', linia='PSD'):
    logger.info(f"[GENERATOR] Starting report generation for {data_raportu} line {linia}")
    logger.info(f"[GENERATOR] Lider: {lider_name}, Uwagi length: {len(uwagi_lidera)}")
    print(f"[GENERATOR] ===== REPORT GENERATION START =====")
    print(f"[GENERATOR] Data: {data_raportu}")
    print(f"[GENERATOR] Lider: {lider_name}")
    print(f"[GENERATOR] Uwagi length: {len(uwagi_lidera)}")
    try:
        conn = get_db_connection()
        logger.info(f"[GENERATOR] Database connection established")
        print(f"[GENERATOR] OK Database connection OK")
    except Exception as e:
        logger.error(f"[GENERATOR] Failed to get DB connection: {e}", exc_info=True)
        print(f"[GENERATOR] ERROR Failed to get DB connection: {e}")
        raise
    
    # Pobieranie danych
    logger.info(f"[GENERATOR] Fetching production data for {data_raportu}")
    print(f"[GENERATOR] Fetching production data...")
    table_plan = get_table_name('plan_produkcji', linia)
    table_szarze = 'szarze_agro' if linia == 'AGRO' else 'szarze'
    table_dosypki = 'dosypki_agro' if linia == 'AGRO' else 'dosypki'
    table_palety = 'palety_agro' if linia == 'AGRO' else 'palety_workowanie'

    sql_plan = f"""
        SELECT 
            p.id, 
            p.sekcja, 
            p.produkt, 
            p.tonaz, 
            CASE 
                WHEN LOWER(TRIM(p.sekcja)) = 'zasyp' THEN (
                    (SELECT COALESCE(SUM(sz.waga), 0) 
                     FROM {table_szarze} sz 
                     WHERE sz.plan_id = p.id AND DATE(sz.data_dodania) = %s)
                    +
                    (SELECT COALESCE(SUM(d.kg), 0)
                     FROM {table_dosypki} d
                     WHERE d.plan_id = p.id 
                       AND d.potwierdzone = 1 
                       AND (d.anulowana = 0 OR d.anulowana IS NULL)
                       AND (
                           DATE(COALESCE(d.data_potwierdzenia, d.data_zlecenia)) = %s
                           OR d.szarza_id IN (SELECT sz.id FROM {table_szarze} sz WHERE DATE(sz.data_dodania) = %s)
                       ))
                )
                ELSE (
                    SELECT COALESCE(SUM(pal.waga), 0) 
                    FROM {table_palety} pal 
                    WHERE pal.plan_id = p.id AND (DATE(pal.data_dodania) = %s OR DATE(pal.data_potwierdzenia) = %s)
                )
            END as tonaz_rzeczywisty,
            p.real_start, 
            p.real_stop, 
            p.nazwa_zlecenia 
        FROM {table_plan} p
        WHERE p.data_planu = %s 
           OR p.id IN (
               SELECT sz.plan_id FROM {table_szarze} sz WHERE DATE(sz.data_dodania) = %s
           )
           OR p.id IN (
               SELECT pal.plan_id FROM {table_palety} pal WHERE DATE(pal.data_dodania) = %s OR DATE(pal.data_potwierdzenia) = %s
           )
        ORDER BY p.kolejnosc, p.id
    """
    df_plan = pd.read_sql(sql_plan, conn, params=(data_raportu, data_raportu, data_raportu, data_raportu, data_raportu, data_raportu, data_raportu, data_raportu, data_raportu))
    logger.info(f"[GENERATOR] Production data: {len(df_plan)} rows from {table_plan}")
    print(f"[GENERATOR] OK Production data: {len(df_plan)} rows from {table_plan}")
    
    # Awarie i przestoje: pobieramy z DowntimeRepository (przestoje_zasyp + przestoje_produkcyjne)
    try:
        from app.repositories.downtime_repository import DowntimeRepository
        dts = DowntimeRepository().get_downtimes(linia, data_raportu, data_raportu)
        awarie_records = []
        for d in dts:
            sek = d.get('sekcja') or 'Zasyp'
            kat = d.get('kategoria') or 'Inne'
            opis = d.get('opis') or d.get('problem') or ''
            prod = d.get('produkt')
            if prod:
                opis = f"[{prod}] {opis}" if opis else f"[{prod}]"
            
            g_start = d.get('godzina_start')
            g_stop = d.get('godzina_stop')
            s_str = str(g_start)[:5] if g_start else ''
            e_str = str(g_stop)[:5] if g_stop else ''
            
            dur = d.get('czas_trwania_min')
            if dur is None and g_start and g_stop:
                try:
                    t1 = datetime.strptime(s_str, '%H:%M')
                    t2 = datetime.strptime(e_str, '%H:%M')
                    diff = int((t2 - t1).total_seconds() / 60)
                    if diff < 0: diff += 1440
                    dur = diff
                except Exception:
                    dur = 0
            awarie_records.append({
                'sekcja': sek,
                'kategoria': kat,
                'problem': opis,
                'start_czas': s_str,
                'stop_czas': e_str,
                'minuty': dur or 0
            })
        df_awarie = pd.DataFrame(awarie_records)
        if df_awarie.empty:
            df_awarie = pd.DataFrame(columns=['sekcja', 'kategoria', 'problem', 'start_czas', 'stop_czas', 'minuty'])
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna zaladowac przestojow z repo: {_e}")
        df_awarie = pd.DataFrame(columns=['sekcja', 'kategoria', 'problem', 'start_czas', 'stop_czas', 'minuty'])
    logger.info(f"[GENERATOR] Issues data: {len(df_awarie)} rows")
    print(f"[GENERATOR] OK Issues data: {len(df_awarie)} rows")
    
    # Lider Zmiany — jeśli nie podano lub nieznany, pobierz z obsada_liderzy dla danej linii
    if not lider_name or str(lider_name).strip().lower() in ('nieznany', 'none', ''):
        try:
            cursor_lider = conn.cursor()
            col_lider = 'lider_psd_id' if str(linia).strip().upper() == 'PSD' else 'lider_agro_id'
            cursor_lider.execute(f"SELECT p.imie_nazwisko FROM obsada_liderzy ol JOIN pracownicy p ON ol.{col_lider} = p.id WHERE ol.data_wpisu = %s", (data_raportu,))
            row_l = cursor_lider.fetchone()
            if row_l and row_l[0]:
                lider_name = row_l[0]
            cursor_lider.close()
        except Exception as _el:
            logger.warning(f"[GENERATOR] Nie można pobrać lidera z obsada_liderzy: {_el}")

    # 1. Obsada — kto był przydzielony do jakiej sekcji przez lidera na danej linii
    try:
        df_obsada = pd.read_sql("""
            SELECT oz.sekcja, p.imie_nazwisko AS pracownik, COALESCE(p.grupa, '') AS grupa, oz.pracownik_id
            FROM obsada_zmiany oz
            JOIN pracownicy p ON oz.pracownik_id = p.id
            WHERE oz.data_wpisu = %s 
              AND (UPPER(COALESCE(oz.linia, 'PSD')) = UPPER(%s) OR (%s = 'PSD' AND (oz.linia IS NULL OR oz.linia = '')))
            ORDER BY 
                CASE 
                    WHEN oz.sekcja = 'Zasyp' THEN 1
                    WHEN oz.sekcja = 'Workowanie' THEN 2
                    WHEN oz.sekcja = 'Magazyn' THEN 3
                    WHEN oz.sekcja = 'Laboratorium' THEN 4
                    WHEN oz.sekcja = 'Handel' THEN 5
                    WHEN INSTR(LOWER(oz.sekcja), 'sterowni') > 0 THEN 1
                    WHEN INSTR(LOWER(oz.sekcja), 'work') > 0 THEN 2
                    WHEN INSTR(LOWER(oz.sekcja), 'zasyp') > 0 THEN 3
                    ELSE 10
                END,
                p.imie_nazwisko
        """, conn, params=(data_raportu, linia, linia))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac obsady: {_e}")
        df_obsada = pd.DataFrame(columns=['sekcja', 'pracownik', 'grupa', 'pracownik_id'])
    logger.info(f"[GENERATOR] Obsada data: {len(df_obsada)} rows")

    # 2. HR / obecności — pracownicy obecni na danej linii (wraz ze stanowiskiem i godzinami)
    try:
        df_hr = pd.read_sql("""
            SELECT 
                p.imie_nazwisko AS pracownik,
                COALESCE(
                    (SELECT oz.sekcja FROM obsada_zmiany oz 
                     WHERE oz.pracownik_id = p.id AND oz.data_wpisu = %s 
                       AND (UPPER(COALESCE(oz.linia, 'PSD')) = UPPER(%s) OR (%s = 'PSD' AND (oz.linia IS NULL OR oz.linia = '')))
                     LIMIT 1),
                    'Brak przydziału'
                ) AS sekcja,
                'Obecny' AS typ,
                COALESCE(o.ilosc_godzin, 8.0) AS ilosc_godzin,
                COALESCE(o.komentarz, '') AS komentarz
            FROM pracownicy p
            JOIN obsada_zmiany oz2 ON oz2.pracownik_id = p.id AND oz2.data_wpisu = %s AND (UPPER(COALESCE(oz2.linia, 'PSD')) = UPPER(%s) OR (%s = 'PSD' AND (oz2.linia IS NULL OR oz2.linia = '')))
            LEFT JOIN obecnosc o ON o.pracownik_id = p.id AND o.data_wpisu = %s
            GROUP BY p.id, p.imie_nazwisko, o.ilosc_godzin, o.komentarz
            ORDER BY sekcja, p.imie_nazwisko
        """, conn, params=(data_raportu, linia, linia, data_raportu, linia, linia, data_raportu))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac HR obecnosci: {_e}")
        df_hr = pd.DataFrame(columns=['pracownik', 'sekcja', 'typ', 'ilosc_godzin', 'komentarz'])
    logger.info(f"[GENERATOR] HR data: {len(df_hr)} rows")
    print(f"[GENERATOR] OK HR data: {len(df_hr)} rows")

    # 3. Nieobecni i Urlopy — typ inny niż 'obecny' dla pracowników danej linii + zatwierdzone wnioski wolne
    try:
        df_nieobecni = pd.read_sql("""
            SELECT DISTINCT
                p.imie_nazwisko AS pracownik,
                CASE 
                    WHEN INSTR(LOWER(TRIM(o.typ)), 'urlop') > 0 THEN 'Urlop'
                    WHEN LOWER(TRIM(o.typ)) IN ('l4', 'chorobowe', 'zwolnienie lekarskie') THEN 'L4'
                    WHEN INSTR(LOWER(TRIM(o.typ)), 'opiek') > 0 THEN 'Opieka'
                    ELSE COALESCE(o.typ, 'Nieobecność')
                END AS typ,
                COALESCE(o.komentarz, '') AS komentarz
            FROM obecnosc o
            JOIN pracownicy p ON o.pracownik_id = p.id
            WHERE o.data_wpisu = %s
              AND (
                  INSTR(LOWER(TRIM(o.typ)), 'urlop') > 0
                  OR LOWER(TRIM(o.typ)) IN ('l4', 'chorobowe', 'opieka', 'nieobecnosc', 'nieobecność', 'zwolnienie', 'kwarantanna', 'inne')
              )
              AND (
                  %s = 'ALL'
                  OR (%s = 'AGRO' AND (p.id IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND UPPER(linia) = 'AGRO') OR COALESCE(p.widoczny_agro, 0) = 1))
                  OR (%s = 'PSD' AND p.id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND UPPER(linia) = 'AGRO') AND COALESCE(p.widoczny_agro, 0) = 0)
              )

            UNION

            SELECT DISTINCT
                p.imie_nazwisko AS pracownik,
                COALESCE(w.typ, 'Urlop') AS typ,
                COALESCE(w.powod, 'Zatwierdzony wniosek') AS komentarz
            FROM wnioski_wolne w
            JOIN pracownicy p ON w.pracownik_id = p.id
            WHERE w.status = 'approved'
              AND %s BETWEEN w.data_od AND w.data_do
              AND (
                  %s = 'ALL'
                  OR (%s = 'AGRO' AND (p.id IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND UPPER(linia) = 'AGRO') OR COALESCE(p.widoczny_agro, 0) = 1))
                  OR (%s = 'PSD' AND p.id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND UPPER(linia) = 'AGRO') AND COALESCE(p.widoczny_agro, 0) = 0)
              )
            ORDER BY typ, pracownik
        """, conn, params=(data_raportu, linia, linia, data_raportu, linia, data_raportu, data_raportu, linia, linia, data_raportu, linia, data_raportu))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac nieobecnych: {_e}")
        df_nieobecni = pd.DataFrame(columns=['pracownik', 'typ', 'komentarz'])
    logger.info(f"[GENERATOR] Nieobecni data: {len(df_nieobecni)} rows")

    # Bufor — co zostało do spakowania
    try:
        table_bufor = get_table_name('bufor', linia)
        df_bufor = pd.read_sql(f"""
            SELECT produkt, COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,
                   tonaz_rzeczywisty, spakowano,
                   GREATEST(tonaz_rzeczywisty - spakowano, 0) AS pozostalo
            FROM {table_bufor}
            WHERE data_planu = %s AND status = 'aktywny' AND tonaz_rzeczywisty > 0
            ORDER BY kolejka
        """, conn, params=(data_raportu,))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac bufora: {_e}")
        df_bufor = pd.DataFrame(columns=['produkt', 'nazwa_zlecenia', 'tonaz_rzeczywisty', 'spakowano', 'pozostalo'])
    logger.info(f"[GENERATOR] Bufor data: {len(df_bufor)} rows")

    # Nadgodziny — kto zostawał po zmianie i dlaczego (filtrowane po linii)
    try:
        df_nadgodziny = pd.read_sql("""
            SELECT p.imie_nazwisko AS pracownik, n.ilosc_nadgodzin,
                   COALESCE(n.powod, '') AS powod, n.status
            FROM nadgodziny n
            JOIN pracownicy p ON n.pracownik_id = p.id
            WHERE n.data = %s
              AND (
                  p.id IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND (linia = %s OR (linia IS NULL AND %s = 'PSD')))
                  OR (%s = 'AGRO' AND COALESCE(p.widoczny_agro, 0) = 1)
                  OR (%s = 'PSD' AND COALESCE(p.widoczny_agro, 0) = 0)
              )
            ORDER BY p.imie_nazwisko
        """, conn, params=(data_raportu, data_raportu, linia, linia, linia, linia))
    except Exception as _e:
        try:
            df_nadgodziny = pd.read_sql("""
                SELECT p.imie_nazwisko AS pracownik, n.ilosc_nadgodzin,
                       COALESCE(n.powod, '') AS powod, n.status
                FROM nadgodziny n
                JOIN pracownicy p ON n.pracownik_id = p.id
                WHERE n.data = %s
                ORDER BY p.imie_nazwisko
            """, conn, params=(data_raportu,))
        except Exception:
            df_nadgodziny = pd.DataFrame(columns=['pracownik', 'ilosc_nadgodzin', 'powod', 'status'])
    # Big Bagi — zużyty wsad na sekcji workowania
    try:
        table_plan = get_table_name('plan_produkcji', linia)
        df_bigbag = pd.read_sql(f"""
            SELECT p.nazwa_zlecenia AS Zlecenie, p.produkt AS Produkt,
                   bb.nr_palety AS Kod_Big_Baga, bb.nr_partii AS Nr_Partii,
                   bb.waga_kg AS Waga_KG, bb.lokalizacja_zrodlowa AS Magazyn,
                   bb.autor_login AS Pobral,
                   DATE_FORMAT(bb.created_at, '%%H:%%i:%%s') AS Godzina_Pobrania
            FROM agro_workowanie_bigbagi bb
            JOIN {table_plan} p ON bb.plan_id = p.id
            WHERE DATE(bb.created_at) = %s AND bb.status = 'ZUZYTY'
            ORDER BY bb.id ASC
        """, conn, params=(data_raportu,))
    except Exception as _e_bb:
        df_bigbag = pd.DataFrame()
    logger.info(f"[GENERATOR] BigBag data: {len(df_bigbag)} rows")

    folder = 'raporty_temp'
    if not os.path.exists(folder): os.makedirs(folder)
    logger.info(f"[GENERATOR] Output folder: {os.path.abspath(folder)}")

    # 1. Excel
    xls_path = os.path.join(folder, f"Raport_{linia}_{data_raportu}.xlsx")
    logger.info(f"[GENERATOR] Creating Excel file: {xls_path}")
    print(f"[GENERATOR] Creating Excel: {os.path.abspath(xls_path)}")
    with pd.ExcelWriter(xls_path, engine='openpyxl') as writer:
        df_plan.to_excel(writer, sheet_name='Produkcja', index=False)
        df_awarie.to_excel(writer, sheet_name='Awarie', index=False)
        df_hr.to_excel(writer, sheet_name='HR - Obecnosc', index=False)
        if not df_obsada.empty:
            df_obsada.to_excel(writer, sheet_name='Obsada - Sekcje', index=False)
        if not df_nieobecni.empty:
            df_nieobecni.to_excel(writer, sheet_name='Nieobecni - Urlopy', index=False)
        if not df_bufor.empty:
            df_bufor.to_excel(writer, sheet_name='Bufor', index=False)
        if not df_nadgodziny.empty:
            df_nadgodziny.to_excel(writer, sheet_name='Nadgodziny', index=False)
        if not df_bigbag.empty:
            df_bigbag.to_excel(writer, sheet_name='BigBagi - Wsad', index=False)
    xls_exists = os.path.exists(xls_path)
    logger.info(f"[GENERATOR] Excel file created: {xls_exists}")
    print(f"[GENERATOR] OK Excel created: {xls_exists} | Path: {os.path.abspath(xls_path)}")

    txt_path = None

    # 2. PDF (używamy helpera z raporty.py)
    try:
        from scripts.raporty import generuj_pdf
        # Przygotuj struktury wymagane przez generuj_pdf (listy krotek)
        # Ustal kolejność produktów na podstawie kolejności planu (pole `kolejnosc` lub `id`)
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            df_order = pd.read_sql(f"SELECT produkt, COALESCE(MIN(kolejnosc), MIN(id)) AS ord FROM {table_plan} WHERE data_planu = %s GROUP BY produkt", conn, params=(data_raportu,))
            product_order = {row['produkt']: row['ord'] for _, row in df_order.iterrows()}
        except Exception:
            product_order = {}

        prod_rows = []
        for _, row in df_plan.iterrows():
            prod_rows.append((
                row.get('sekcja', ''), 
                row.get('produkt', ''), 
                row.get('tonaz', None), 
                row.get('tonaz_rzeczywisty', None),
                row.get('real_start', None),
                row.get('real_stop', None),
                row.get('nazwa_zlecenia', ''),
                row.get('id', '')
            ))

        # Sortuj: najpierw według kolejności produktu w planie (`kolejnosc`/id),
        # potem po nazwie produktu, a wewnątrz produktu uporządkuj sekcje: Zasyp -> Workowanie -> Magazyn
        order_map = {'Zasyp': 0, 'Workowanie': 1, 'Czyszczenie': 1, 'Magazyn': 2}
        try:
            prod_rows.sort(key=lambda r: (
                product_order.get(r[1], 9999),
                (str(r[1]).lower() if r[1] is not None else ''),
                order_map.get(r[0], 99)
            ))
        except Exception:
            pass

        awarie_rows = []
        for _, row in df_awarie.iterrows():
            awarie_rows.append((row.get('sekcja', ''), row.get('kategoria', ''), row.get('problem', ''), row.get('start_czas', ''), row.get('stop_czas', ''), row.get('minuty', None)))

        hr_rows = []
        for _, row in df_hr.iterrows():
            hr_rows.append((row.get('pracownik', ''), row.get('sekcja', ''), row.get('typ', 'Obecny'), row.get('ilosc_godzin', 8.0), row.get('komentarz', '')))

        bufor_rows = [(r.get('produkt', ''), r.get('nazwa_zlecenia', ''), r.get('tonaz_rzeczywisty', 0), r.get('spakowano', 0), r.get('pozostalo', 0)) for _, r in df_bufor.iterrows()]
        obsada_rows = [(r.get('sekcja', ''), r.get('pracownik', ''), r.get('grupa', '')) for _, r in df_obsada.iterrows()]
        nieobecni_rows = [(r.get('pracownik', ''), r.get('typ', ''), r.get('komentarz', '')) for _, r in df_nieobecni.iterrows()]
        nadgodziny_rows = [(r.get('pracownik', ''), r.get('ilosc_nadgodzin', 0), r.get('powod', ''), r.get('status', '')) for _, r in df_nadgodziny.iterrows()]

        try:
            table_palety = get_table_name('palety_workowanie', linia)
            sql_palety = f"""
                SELECT p.id as plan_id, p.nazwa_zlecenia, p.produkt, COUNT(pw.id) as ilosc_palet, SUM(pw.waga) as laczna_waga
                FROM {table_palety} pw
                JOIN {table_plan} p ON pw.plan_id = p.id
                WHERE DATE(pw.data_dodania) = %s
                GROUP BY p.id, p.nazwa_zlecenia, p.produkt
                ORDER BY MIN(pw.id) ASC
            """
            df_palety = pd.read_sql(sql_palety, conn, params=(data_raportu,))
            palety_rows = []
            for _, r in df_palety.iterrows():
                zlec = r.get('nazwa_zlecenia')
                if not zlec or not str(zlec).strip():
                    zlec = f"ID: {r.get('plan_id', '')}"
                palety_rows.append((zlec, r.get('produkt', ''), r.get('ilosc_palet', 0), r.get('laczna_waga', 0)))
        except Exception as e:
            logger.error(f"[GENERATOR] Error fetching palety_rows: {e}")
            palety_rows = []

        # Pobierz wskanowane Big Bagi dla tego dnia
        bigbag_rows = []
        try:
            sql_bb = f"""
                SELECT p.nazwa_zlecenia, p.produkt, bb.nr_palety, bb.nr_partii, bb.waga_kg, bb.autor_login
                FROM agro_workowanie_bigbagi bb
                JOIN {table_plan} p ON bb.plan_id = p.id
                WHERE DATE(bb.created_at) = %s AND bb.status = 'ZUZYTY'
                ORDER BY bb.id ASC
            """
            df_bb = pd.read_sql(sql_bb, conn, params=(data_raportu,))
            for _, r in df_bb.iterrows():
                zlec = r.get('nazwa_zlecenia') or 'Zlecenie'
                bigbag_rows.append((zlec, r.get('produkt', ''), r.get('nr_palety', ''), r.get('nr_partii', ''), r.get('waga_kg', 0), r.get('autor_login', '')))
        except Exception as e_bb:
            logger.warning(f"[GENERATOR] Error fetching bigbag_rows: {e_bb}")
            bigbag_rows = []

        print(f"[GENERATOR] About to call generuj_pdf with data={data_raportu}, prod_rows count={len(prod_rows)}, awarie_rows count={len(awarie_rows)}, hr_rows count={len(hr_rows)}, bigbag_rows count={len(bigbag_rows)}")
        import sys
        sys.stdout.flush()
        sys.stderr.flush()
        
        pdf_name = generuj_pdf(data_raportu, uwagi_lidera, lider_name, prod_rows, awarie_rows, hr_rows,
                               folder, linia,
                               obsada_rows=obsada_rows, nieobecni_rows=nieobecni_rows,
                               bufor_rows=bufor_rows, nadgodziny_rows=nadgodziny_rows,
                               palety_rows=palety_rows,
                               bigbag_rows=bigbag_rows)
        
        print(f"[GENERATOR] generuj_pdf returned: {pdf_name}")
        sys.stdout.flush()
        
        logger.info(f"[GENERATOR] pdf_name returned: {pdf_name} (type={type(pdf_name).__name__})")
        # Użyj absolutnych ścieżek — CWD serwera Flask może się różnić od root projektu
        _base = Path(__file__).resolve().parent.parent
        _raporty_abs = _base / 'raporty'
        if pdf_name:
            pdf_abs = _raporty_abs / pdf_name
            new_pdf_name = f"Raport_{linia}_{data_raportu}.pdf"
            new_pdf_abs = _raporty_abs / new_pdf_name
            if pdf_abs.exists():
                if pdf_abs.resolve() != new_pdf_abs.resolve():
                    import shutil
                    shutil.move(str(pdf_abs), str(new_pdf_abs))
                pdf_path = str(new_pdf_abs)
            elif new_pdf_abs.exists():
                # File already exists under target destination path
                pdf_path = str(new_pdf_abs)
            else:
                # Fallback: check _new.pdf if temporary lock was present during save
                fallback = _raporty_abs / pdf_name.replace('.pdf', '_new.pdf')
                if fallback.exists():
                    import shutil
                    shutil.move(str(fallback), str(new_pdf_abs))
                    pdf_path = str(new_pdf_abs)
                else:
                    logger.warning("[GENERATOR] PDF file not found at %s or %s", pdf_abs, fallback)
                    pdf_path = None
        else:
            pdf_path = None
        logger.info(f"[GENERATOR] PDF generated successfully: {pdf_name}")
    except Exception as e:
        import traceback
        logger.error(f"[GENERATOR] PDF generation failed: {e}", exc_info=True)
        traceback.print_exc()
        pdf_path = None

    # Zamykamy po wszystkich operacjach na DB
    try:
        conn.close()
    except Exception:
        pass

    logger.info(f"[GENERATOR] Report generation completed for {data_raportu}")
    logger.info(f"[GENERATOR] Files: xls={xls_path}, txt={txt_path}, pdf={pdf_path}")
    print(f"[GENERATOR] ===== REPORT GENERATION COMPLETE =====")
    print(f"[GENERATOR] Returning: xls={xls_path}, txt={txt_path}, pdf={pdf_path}")
    print(f"[GENERATOR] XLS exists: {os.path.exists(xls_path) if xls_path else False}")
    print(f"[GENERATOR] TXT exists: {os.path.exists(txt_path) if txt_path else False}")
    print(f"[GENERATOR] PDF exists: {os.path.exists(pdf_path) if pdf_path else False}")
    return xls_path, txt_path, pdf_path


def generuj_excel_zmiany(data_raportu, linia='PSD'):
    """Kompatybilna z app.py: zwraca ścieżkę do wygenerowanego pliku Excel (lub None)."""
    try:
        xls, txt, pdf = generuj_paczke_raportow(data_raportu, '', linia=linia)
        # Przenieś wygenerowane pliki do trwałego folderu `raporty` dostępnego przez aplikację
        import shutil
        raporty_dir = 'raporty'
        if not os.path.exists(raporty_dir):
            os.makedirs(raporty_dir)
        try:
            new_xls = os.path.join(raporty_dir, os.path.basename(xls))
            shutil.move(xls, new_xls)
        except Exception:
            new_xls = xls
        # PDF is already generated in 'raporty' by generuj_pdf (if available)
        new_pdf = None
        try:
            if pdf:
                # jeśli pdf jest już pełną ścieżką - zachowaj; jeśli tylko nazwą - dołącz katalog raporty
                new_pdf = pdf if os.path.isabs(pdf) else os.path.join(raporty_dir, os.path.basename(pdf))
                if not os.path.exists(new_pdf):
                    new_pdf = None
        except Exception:
            new_pdf = None

        return new_xls, new_txt, new_pdf
    except Exception as e:
        print(f"Błąd generowania excela: {e}")
        return None, None, None


def otworz_outlook_z_raportem(sciezka_xls, uwagi_lidera):
    """Próbuje otworzyć Outlook i przygotować maila z załącznikiem.
    Jeśli środowisko nie obsługuje COM/Outlook, funkcja nie podniesie wyjątku.
    """
    try:
        import win32com.client
    except Exception as e:
        print(f"win32com unavailable: {e}")
        return False

    try:
        outlook = win32com.client.Dispatch('Outlook.Application')
        mail = outlook.CreateItem(0)
        # We don't have linia here easily unless we pass it, but let's just keep generic name or use XLS basename
        subj_line = os.path.basename(sciezka_xls).replace('.xlsx', '').replace('Raport_', 'Raport ')
        mail.Subject = f"{subj_line} - {datetime.now().date()}"
        mail.Body = uwagi_lidera or ''
        if sciezka_xls and os.path.exists(sciezka_xls):
            mail.Attachments.Add(os.path.abspath(sciezka_xls))
        mail.Display(False)
        return True
    except Exception as e:
        print(f"Błąd otwierania Outlooka: {e}")
        return False