import pandas as pd
import os
from datetime import datetime
from db import get_db_connection

def generuj_paczke_raportow(data_raportu, uwagi_lidera):
    conn = get_db_connection()
    
    # Pobieranie danych
    df_plan = pd.read_sql("SELECT sekcja, produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE data_planu = %s", conn, params=(data_raportu,))
    # Awarie: spróbuj pobrać szczegółowe kolumny, ale jeśli ich nie ma w schemacie, użyj prostszego SELECT
    try:
        df_awarie = pd.read_sql("SELECT sekcja, kategoria, problem, start_czas, stop_czas, minuty FROM dziennik_zmiany WHERE data_wpisu = %s", conn, params=(data_raportu,))
    except Exception:
        df_awarie = pd.read_sql("SELECT sekcja, kategoria, problem FROM dziennik_zmiany WHERE data_wpisu = %s", conn, params=(data_raportu,))
    # HR / obecności
    df_hr = pd.read_sql("SELECT p.imie_nazwisko as pracownik, o.typ, o.ilosc_godzin FROM obecnosc o JOIN pracownicy p ON o.pracownik_id=p.id WHERE o.data_wpisu = %s", conn, params=(data_raportu,))

    folder = 'raporty_temp'
    if not os.path.exists(folder): os.makedirs(folder)

    # 1. Excel
    xls_path = os.path.join(folder, f"Raport_{data_raportu}.xlsx")
    with pd.ExcelWriter(xls_path, engine='openpyxl') as writer:
        df_plan.to_excel(writer, sheet_name='Produkcja', index=False)
        df_awarie.to_excel(writer, sheet_name='Awarie', index=False)
        df_hr.to_excel(writer, sheet_name='HR', index=False)

    # 2. Notatnik (Treść do maila)
    txt_path = os.path.join(folder, f"Do_Maila_{data_raportu}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"RAPORT PRODUKCYJNY - {data_raportu}\n")
        f.write("="*30 + "\n\n")
        f.write(f"UWAGI LIDERA:\n{uwagi_lidera}\n\n")
        f.write(f"PRODUKCJA: {int(df_plan['tonaz_rzeczywisty'].sum())} kg\n")
        f.write(f"AWRIE/PRZESTOJE: {len(df_awarie)} wpisów.")

    # 3. PDF (używamy helpera z raporty.py)
    try:
        from raporty import generuj_pdf
        # Przygotuj struktury wymagane przez generuj_pdf (listy krotek)
        # Ustal kolejność produktów na podstawie kolejności planu (pole `kolejnosc` lub `id`)
        try:
            df_order = pd.read_sql("SELECT produkt, COALESCE(MIN(kolejnosc), MIN(id)) AS ord FROM plan_produkcji WHERE data_planu = %s GROUP BY produkt", conn, params=(data_raportu,))
            product_order = {row['produkt']: row['ord'] for _, row in df_order.iterrows()}
        except Exception:
            product_order = {}

        prod_rows = []
        for _, row in df_plan.iterrows():
            prod_rows.append((row.get('sekcja', ''), row.get('produkt', ''), row.get('tonaz', None), row.get('tonaz_rzeczywisty', None)))

        # Sortuj: najpierw według kolejności produktu w planie (`kolejnosc`/id),
        # potem po nazwie produktu, a wewnątrz produktu uporządkuj sekcje: Zasyp -> Workowanie -> Magazyn
        order_map = {'Zasyp': 0, 'Workowanie': 1, 'Magazyn': 2}
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

        pdf_name = generuj_pdf(data_raportu, uwagi_lidera, '', prod_rows, awarie_rows, hr_rows)
        pdf_path = os.path.join('raporty', pdf_name) if pdf_name else None
    except Exception:
        import traceback
        traceback.print_exc()
        pdf_path = None

    # Zamykamy po wszystkich operacjach na DB
    try:
        conn.close()
    except Exception:
        pass

    return xls_path, txt_path, pdf_path


def generuj_excel_zmiany(data_raportu):
    """Kompatybilna z app.py: zwraca ścieżkę do wygenerowanego pliku Excel (lub None)."""
    try:
        xls, txt, pdf = generuj_paczke_raportow(data_raportu, '')
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
        mail.Subject = f"Raport produkcyjny - {datetime.now().date()}"
        mail.Body = uwagi_lidera or ''
        if sciezka_xls and os.path.exists(sciezka_xls):
            mail.Attachments.Add(os.path.abspath(sciezka_xls))
        mail.Display(False)
        return True
    except Exception as e:
        print(f"Błąd otwierania Outlooka: {e}")
        return False