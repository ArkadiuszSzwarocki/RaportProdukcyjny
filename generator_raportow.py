import pandas as pd
import os
from datetime import datetime
from db import get_db_connection

def generuj_paczke_raportow(data_raportu, uwagi_lidera):
    conn = get_db_connection()
    
    # Pobieranie danych
    df_plan = pd.read_sql("SELECT produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE data_planu = %s", conn, params=(data_raportu,))
    df_awarie = pd.read_sql("SELECT sekcja, kategoria, problem FROM dziennik_zmiany WHERE data_wpisu = %s", conn, params=(data_raportu,))
    conn.close()

    folder = 'raporty_temp'
    if not os.path.exists(folder): os.makedirs(folder)

    # 1. Excel
    xls_path = os.path.join(folder, f"Raport_{data_raportu}.xlsx")
    with pd.ExcelWriter(xls_path, engine='openpyxl') as writer:
        df_plan.to_excel(writer, sheet_name='Produkcja', index=False)
        df_awarie.to_excel(writer, sheet_name='Awarie', index=False)

    # 2. Notatnik (Treść do maila)
    txt_path = os.path.join(folder, f"Do_Maila_{data_raportu}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"RAPORT PRODUKCYJNY - {data_raportu}\n")
        f.write("="*30 + "\n\n")
        f.write(f"UWAGI LIDERA:\n{uwagi_lidera}\n\n")
        f.write(f"PRODUKCJA: {int(df_plan['tonaz_rzeczywisty'].sum())} kg\n")
        f.write(f"AWRIE/PRZESTOJE: {len(df_awarie)} wpisów.")

    return xls_path, txt_path


def generuj_excel_zmiany(data_raportu):
    """Kompatybilna z app.py: zwraca ścieżkę do wygenerowanego pliku Excel (lub None)."""
    try:
        xls, txt = generuj_paczke_raportow(data_raportu, '')
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
        return new_xls
    except Exception as e:
        print(f"Błąd generowania excela: {e}")
        return None


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