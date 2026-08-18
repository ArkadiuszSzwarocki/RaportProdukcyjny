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
    table_palety = get_table_name('palety_workowanie', linia)
    sql_plan = f"""
        SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, real_start, real_stop, nazwa_zlecenia 
        FROM {table_plan} 
        WHERE data_planu = %s 
           OR DATE(real_start) = %s 
           OR DATE(real_stop) = %s 
           OR id IN (
               SELECT plan_id FROM {table_palety} WHERE DATE(data_dodania) = %s
           )
    """
    df_plan = pd.read_sql(sql_plan, conn, params=(data_raportu, data_raportu, data_raportu, data_raportu))
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
    
    # HR / obecności — wszyscy wpisani (w tym nieobecni)
    df_hr = pd.read_sql("SELECT p.imie_nazwisko as pracownik, o.typ, o.ilosc_godzin FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu = %s", conn, params=(data_raportu,))
    logger.info(f"[GENERATOR] HR data: {len(df_hr)} rows")
    print(f"[GENERATOR] OK HR data: {len(df_hr)} rows")

    # Obsada — kto był przydzielony do jakiej sekcji przez lidera
    try:
        df_obsada = pd.read_sql("""
            SELECT oz.sekcja, p.imie_nazwisko AS pracownik, COALESCE(p.grupa, '') AS grupa
            FROM obsada_zmiany oz
            JOIN pracownicy p ON oz.pracownik_id = p.id
            WHERE oz.data_wpisu = %s
            ORDER BY oz.sekcja, p.imie_nazwisko
        """, conn, params=(data_raportu,))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac obsady: {_e}")
        df_obsada = pd.DataFrame(columns=['sekcja', 'pracownik', 'grupa'])
    logger.info(f"[GENERATOR] Obsada data: {len(df_obsada)} rows")

    # Nieobecni — typ inny niż 'obecny'
    try:
        # Normalizujemy pole `typ` po stronie bazy (trim + lower),
        # by uniknąć dopasowań z powodu wielkości liter lub nadmiarowych spacji.
        df_nieobecni = pd.read_sql("""
            SELECT p.imie_nazwisko AS pracownik,
                   COALESCE(TRIM(LOWER(o.typ)), '') AS typ,
                   COALESCE(o.komentarz, '') AS komentarz
            FROM obecnosc o
            JOIN pracownicy p ON o.pracownik_id = p.id
            WHERE o.data_wpisu = %s AND COALESCE(LOWER(TRIM(o.typ)), '') NOT IN ('obecny', 'obecnosc')
            ORDER BY typ, p.imie_nazwisko
        """, conn, params=(data_raportu,))
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

    # Nadgodziny — kto zostawał po zmianie i dlaczego
    try:
        df_nadgodziny = pd.read_sql("""
            SELECT p.imie_nazwisko AS pracownik, n.ilosc_nadgodzin,
                   COALESCE(n.powod, '') AS powod, n.status
            FROM nadgodziny n
            JOIN pracownicy p ON n.pracownik_id = p.id
            WHERE n.data = %s
            ORDER BY p.imie_nazwisko
        """, conn, params=(data_raportu,))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac nadgodzin: {_e}")
        df_nadgodziny = pd.DataFrame(columns=['pracownik', 'ilosc_nadgodzin', 'powod', 'status'])
    logger.info(f"[GENERATOR] Nadgodziny data: {len(df_nadgodziny)} rows")

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
            df_nieobecni.to_excel(writer, sheet_name='Nieobecni', index=False)
        if not df_bufor.empty:
            df_bufor.to_excel(writer, sheet_name='Bufor', index=False)
        if not df_nadgodziny.empty:
            df_nadgodziny.to_excel(writer, sheet_name='Nadgodziny', index=False)
    xls_exists = os.path.exists(xls_path)
    logger.info(f"[GENERATOR] Excel file created: {xls_exists}")
    print(f"[GENERATOR] OK Excel created: {xls_exists} | Path: {os.path.abspath(xls_path)}")

    # 2. Notatnik (Treść do maila)
    txt_path = os.path.join(folder, f"Do_Maila_{linia}_{data_raportu}.txt")
    logger.info(f"[GENERATOR] Creating TXT file: {txt_path}")
    print(f"[GENERATOR] Creating TXT: {os.path.abspath(txt_path)}")

    # Rozbicie produkcji na Zasyp i Workowanie
    try:
        zasyp_mask = df_plan['sekcja'].astype(str).str.strip().str.lower() == 'zasyp'
        suma_zasyp = int(df_plan[zasyp_mask]['tonaz_rzeczywisty'].sum())
    except Exception:
        suma_zasyp = 0

    try:
        workowanie_mask = df_plan['sekcja'].astype(str).str.strip().str.lower() == 'workowanie'
        suma_workowanie = int(df_plan[workowanie_mask]['tonaz_rzeczywisty'].sum())
    except Exception:
        suma_workowanie = 0

    suma_laczna = int(df_plan['tonaz_rzeczywisty'].sum()) if not df_plan.empty else (suma_zasyp + suma_workowanie)

    # Pobranie zarejestrowanych przestojów z tabel przestoje_produkcyjne i przestoje_zasyp
    downtimes = []
    total_downtime_min = 0
    try:
        from app.repositories.downtime_repository import DowntimeRepository
        downtimes = DowntimeRepository().get_downtimes(linia, data_raportu, data_raportu)
        for dt in downtimes:
            dur = dt.get('czas_trwania_min')
            if dur is None and dt.get('godzina_start') and dt.get('godzina_stop'):
                try:
                    t1 = datetime.strptime(str(dt['godzina_start'])[:5], '%H:%M')
                    t2 = datetime.strptime(str(dt['godzina_stop'])[:5], '%H:%M')
                    diff = int((t2 - t1).total_seconds() / 60)
                    if diff < 0:
                        diff += 1440
                    dur = diff
                except Exception:
                    dur = 0
            dur_val = int(dur or 0)
            total_downtime_min += dur_val
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac przestojow do maila: {_e}")

    dt_hours = total_downtime_min // 60
    dt_mins = total_downtime_min % 60
    if dt_hours > 0:
        dt_sum_str = f"{dt_hours}h {dt_mins} min ({total_downtime_min} min)"
    else:
        dt_sum_str = f"{dt_mins} min"

    # Obliczenie wydajności Zasypu
    from app.services.shift_time_service import ShiftTimeService
    zasyp_dt_min = sum(int(dt.get('czas_trwania_min') or 0) for dt in (downtimes or []) if (dt.get('sekcja') or '').strip().lower() == 'zasyp')
    prod_metrics = ShiftTimeService.calculate_productivity(
        mass_kg=suma_zasyp,
        awarie_min=zasyp_dt_min,
        date_str=data_raportu
    )
    zasyp_brutto_min = prod_metrics['brutto_min']
    zasyp_netto_min = prod_metrics['netto_min']
    wydajnosc_efektywna = prod_metrics['wydajnosc_efektywna']
    wydajnosc_rzeczywista = prod_metrics['wydajnosc_rzeczywista']
    start_str = prod_metrics['start_str']
    end_str = prod_metrics['end_str']

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"RAPORT PRODUKCYJNY — {linia} — {data_raportu}\n")
        f.write("=" * 50 + "\n\n")
        
        f.write("PRODUKCJA NA ZMIANIE:\n")
        f.write(f"  * Zasyp (wytworzono): {suma_zasyp} kg\n")
        if suma_zasyp > 0:
            f.write(f"    - Wydajnosc efektywna (netto): {wydajnosc_efektywna:.1f} kg/h (wykonane w {zasyp_netto_min} min produkcyjnych [{zasyp_brutto_min} min - {zasyp_dt_min} min awarie])\n")
            f.write(f"    - Wydajnosc rzeczywista (brutto / {start_str}-{end_str}): {wydajnosc_rzeczywista:.1f} kg/h ({suma_zasyp} kg / {zasyp_brutto_min} min * 60)\n")
        f.write(f"  * Workowanie (spakowano): {suma_workowanie} kg\n\n")

        f.write("PRZESTOJE I AWARIE:\n")
        f.write(f"  * Laczny czas przestojow: {dt_sum_str}\n")
        f.write(f"  * Liczba zarejestrowanych przestojow: {len(downtimes)}\n")
        if downtimes:
            for idx, dt in enumerate(downtimes, 1):
                sek = dt.get('sekcja') or 'Produkcja'
                kat = dt.get('kategoria') or 'Inne'
                op = dt.get('opis') or ''
                g_start = str(dt.get('godzina_start') or '')[:5]
                g_stop = str(dt.get('godzina_stop') or '')[:5] if dt.get('godzina_stop') else 'w toku'
                dur = dt.get('czas_trwania_min')
                dur_txt = f"{dur} min" if dur is not None else "w trakcie"
                prod = f" [{dt.get('produkt')}]" if dt.get('produkt') else ""
                f.write(f"    {idx}. [{sek}] {g_start} - {g_stop} ({dur_txt}) — {kat}: {op}{prod}\n")
        else:
            f.write("    (Brak zarejestrowanych przestojow)\n")
        f.write("\n")

        if uwagi_lidera and uwagi_lidera.strip():
            f.write(f"NOTATKI ZMIANOWE / UWAGI:\n{uwagi_lidera.strip()}\n\n")
        else:
            f.write("NOTATKI ZMIANOWE / UWAGI:\n(Brak uwag lidera)\n\n")

        f.write("Informacja: Wiecej szczegolowych informacji (m.in. zestawienie zuzycia surowcow, czasy cykli, obsada pracownicza) znajduje sie w szczegolowym raporcie w zalacznikach (PDF / Excel).\n")

    txt_exists = os.path.exists(txt_path)
    logger.info(f"[GENERATOR] TXT file created: {txt_exists}")
    print(f"[GENERATOR] OK TXT created: {txt_exists} | Path: {os.path.abspath(txt_path)}")

    # 3. PDF (używamy helpera z raporty.py)
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
            hr_rows.append((row.get('pracownik', ''), row.get('typ', ''), row.get('ilosc_godzin', None)))

        bufor_rows = [(r.get('produkt', ''), r.get('nazwa_zlecenia', ''), r.get('tonaz_rzeczywisty', 0), r.get('spakowano', 0), r.get('pozostalo', 0)) for _, r in df_bufor.iterrows()]
        obsada_rows = [(r.get('sekcja', ''), r.get('pracownik', ''), r.get('funkcja', '')) for _, r in df_obsada.iterrows()]
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

        print(f"[GENERATOR] About to call generuj_pdf with data={data_raportu}, prod_rows count={len(prod_rows)}, awarie_rows count={len(awarie_rows)}, hr_rows count={len(hr_rows)}")
        import sys
        sys.stdout.flush()
        sys.stderr.flush()
        
        pdf_name = generuj_pdf(data_raportu, uwagi_lidera, lider_name, prod_rows, awarie_rows, hr_rows,
                               folder, linia,
                               obsada_rows=obsada_rows, nieobecni_rows=nieobecni_rows,
                               bufor_rows=bufor_rows, nadgodziny_rows=nadgodziny_rows,
                               palety_rows=palety_rows)
        
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
                import shutil
                shutil.move(str(pdf_abs), str(new_pdf_abs))
                pdf_path = str(new_pdf_abs)
            elif new_pdf_abs.exists():
                # Już istnieje pod docelową nazwą (np. po poprzednim wywołaniu)
                pdf_path = str(new_pdf_abs)
            else:
                # Fallback: szukaj pod _new.pdf (plik mógł być zablokowany)
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
        try:
            new_txt = os.path.join(raporty_dir, os.path.basename(txt))
            shutil.move(txt, new_txt)
        except Exception:
            new_txt = txt
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