import pandas as pd
import os
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
    df_plan = pd.read_sql(f"SELECT sekcja, produkt, tonaz, tonaz_rzeczywisty FROM {table_plan} WHERE data_planu = %s", conn, params=(data_raportu,))
    logger.info(f"[GENERATOR] Production data: {len(df_plan)} rows from {table_plan}")
    print(f"[GENERATOR] OK Production data: {len(df_plan)} rows from {table_plan}")
    
    # Awarie: spróbuj pobrać szczegółowe kolumny, ale jeśli ich nie ma w schemacie, użyj prostszego SELECT
    try:
        # db schema uses `czas_start`/`czas_stop` and we compute `minuty` dynamically
        df_awarie = pd.read_sql(
            "SELECT sekcja, kategoria, problem, czas_start AS start_czas, czas_stop AS stop_czas, "
            "TIMESTAMPDIFF(MINUTE, czas_start, czas_stop) AS minuty "
            "FROM dziennik_zmiany WHERE data_wpisu = %s AND linia = %s",
            conn, params=(data_raportu, linia)
        )
    except Exception:
        df_awarie = pd.read_sql("SELECT sekcja, kategoria, problem FROM dziennik_zmiany WHERE data_wpisu = %s AND linia = %s", conn, params=(data_raportu, linia))
    logger.info(f"[GENERATOR] Issues data: {len(df_awarie)} rows")
    print(f"[GENERATOR] OK Issues data: {len(df_awarie)} rows")
    
    # HR / obecności — wszyscy wpisani (w tym nieobecni)
    df_hr = pd.read_sql("SELECT p.imie_nazwisko as pracownik, o.typ, o.ilosc_godzin FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu = %s", conn, params=(data_raportu,))
    logger.info(f"[GENERATOR] HR data: {len(df_hr)} rows")
    print(f"[GENERATOR] OK HR data: {len(df_hr)} rows")

    # Obsada — kto był przydzielony do jakiej sekcji
    try:
        df_obsada = pd.read_sql("""
            SELECT oz.sekcja, p.imie_nazwisko AS pracownik
            FROM obsada_zmiany oz
            JOIN pracownicy p ON oz.pracownik_id = p.id
            WHERE oz.data_wpisu = %s AND oz.linia = %s
            ORDER BY oz.sekcja, p.imie_nazwisko
        """, conn, params=(data_raportu, linia))
    except Exception as _e:
        logger.warning(f"[GENERATOR] Nie mozna pobrac obsady: {_e}")
        df_obsada = pd.DataFrame(columns=['sekcja', 'pracownik'])
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
            WHERE o.data_wpisu = %s AND COALESCE(LOWER(TRIM(o.typ)), '') != 'obecny'
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
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"RAPORT PRODUKCYJNY - {linia} - {data_raportu}\n")
        f.write("="*30 + "\n\n")
        f.write(f"NOTATKI ZMIANOWE:\n{uwagi_lidera}\n\n")
        f.write(f"PRODUKCJA: {int(df_plan['tonaz_rzeczywisty'].sum())} kg\n")
        f.write(f"AWRIE/PRZESTOJE: {len(df_awarie)} wpisów.")
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
            prod_rows.append((row.get('sekcja', ''), row.get('produkt', ''), row.get('tonaz', None), row.get('tonaz_rzeczywisty', None)))

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
        obsada_rows = [(r.get('sekcja', ''), r.get('pracownik', '')) for _, r in df_obsada.iterrows()]
        nieobecni_rows = [(r.get('pracownik', ''), r.get('typ', ''), r.get('komentarz', '')) for _, r in df_nieobecni.iterrows()]
        nadgodziny_rows = [(r.get('pracownik', ''), r.get('ilosc_nadgodzin', 0), r.get('powod', ''), r.get('status', '')) for _, r in df_nadgodziny.iterrows()]

        print(f"[GENERATOR] About to call generuj_pdf with data={data_raportu}, prod_rows count={len(prod_rows)}, awarie_rows count={len(awarie_rows)}, hr_rows count={len(hr_rows)}")
        import sys
        sys.stdout.flush()
        sys.stderr.flush()
        
        pdf_name = generuj_pdf(data_raportu, uwagi_lidera, lider_name, prod_rows, awarie_rows, hr_rows,
                               obsada_rows=obsada_rows, nieobecni_rows=nieobecni_rows,
                               bufor_rows=bufor_rows, nadgodziny_rows=nadgodziny_rows)
        
        print(f"[GENERATOR] generuj_pdf returned: {pdf_name}")
        sys.stdout.flush()
        
        logger.info(f"[GENERATOR] pdf_name returned: {pdf_name} (type={type(pdf_name).__name__})")
        pdf_path = os.path.join('raporty', pdf_name) if pdf_name else None
        # Rename PDF to include line name if possible or handle it in raporty.py
        if pdf_path and os.path.exists(pdf_path):
             new_pdf_name = f"Raport_{linia}_{data_raportu}.pdf"
             new_pdf_path = os.path.join('raporty', new_pdf_name)
             import shutil
             shutil.move(pdf_path, new_pdf_path)
             pdf_path = new_pdf_path
        logger.info(f"[GENERATOR] pdf_path constructed: {pdf_path}")
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