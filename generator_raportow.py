import pandas as pd
import os
from datetime import datetime
from db import get_db_connection

def generuj_excel_zmiany(data_raportu):
    conn = get_db_connection()
    
    # 1. Pobieranie danych o Produkcji
    query_plan = """
        SELECT produkt, typ_produkcji as typ, tonaz as plan_kg, tonaz_rzeczywisty as wykonanie_kg, 
        (COALESCE(tonaz_rzeczywisty, 0) - tonaz) as roznica_kg, status, wyjasnienie_rozbieznosci
        FROM plan_produkcji 
        WHERE data_planu = %s AND sekcja = 'Zasyp'
    """
    
    # 2. Pobieranie danych o Awariach i Przestojach
    query_awarie = """
        SELECT sekcja, kategoria, problem, TIME_FORMAT(czas_start, '%H:%i') as start, 
        TIME_FORMAT(czas_stop, '%H:%i') as stop,
        TIMESTAMPDIFF(MINUTE, czas_start, czas_stop) as trwanie_min
        FROM dziennik_zmiany
        WHERE data_wpisu = %s
    """
    
    try:
        df_plan = pd.read_sql(query_plan, conn, params=(data_raportu,))
        df_awarie = pd.read_sql(query_awarie, conn, params=(data_raportu,))
    except Exception as e:
        print(f"Błąd SQL: {e}")
        return None
    finally:
        conn.close()
    
    if not os.path.exists('raporty'):
        os.makedirs('raporty')
        
    nazwa_pliku = f"Raport_Produkcyjny_{data_raportu}.xlsx"
    sciezka_pliku = os.path.abspath(os.path.join('raporty', nazwa_pliku))
    
    try:
        with pd.ExcelWriter(sciezka_pliku, engine='openpyxl') as writer:
            df_plan.to_excel(writer, sheet_name='Produkcja', index=False)
            df_awarie.to_excel(writer, sheet_name='Awarie i Przestoje', index=False)
        return sciezka_pliku
    except Exception as e:
        print(f"Błąd zapisu Excel: {e}")
        return None

def otworz_outlook_z_raportem(sciezka_zalacznika, uwagi_lidera):
    """Ta funkcja zadziała tylko jeśli Outlook jest zainstalowany na serwerze"""
    try:
        import win32com.client as win32
        outlook = win32.Dispatch('outlook.application')
        mail = outlook.CreateItem(0)
        mail.Subject = f'Raport Produkcyjny - {datetime.now().strftime("%Y-%m-%d")}'
        mail.Body = f"Dzień dobry,\n\nPrzesyłam raport z dzisiejszej zmiany.\n\nUwagi Lidera:\n{uwagi_lidera}\n\nPozdrawiam,\nSystem MES"
        
        if sciezka_zalacznika and os.path.exists(sciezka_zalacznika):
            mail.Attachments.Add(sciezka_zalacznika)
        
        mail.Display() # Otwiera okno Outlooka do edycji/wysłania
        return True
    except Exception as e:
        print(f"Nie udało się otworzyć Outlooka: {e}")
        return False