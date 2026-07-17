import sys
import os
from datetime import date, datetime, timedelta

# Konfiguracja ścieżki i bazy
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection

def generate_historical_separator_cleanings():
    # Pobieramy daty od 1 czerwca 2026 r. (bo dziś to czerwiec 2026)
    start_date = date(2026, 6, 1)
    end_date = date.today()
    
    # Wygeneruj piątki pomiędzy start_date a end_date
    current = start_date
    fridays = []
    while current <= end_date:
        if current.weekday() == 4: # Piątek to 4 w pythonowym datetime (0 = Monday)
            fridays.append(current)
        current += timedelta(days=1)
    
    users = ['SzwarArk', 'BoczkMar']
    lines = ['SE01', 'SEPSD']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # By zapobiec duplikatom, najpierw czyścimy istniejące
        cursor.execute("TRUNCATE TABLE czyszczenie_separatorow;")
        conn.commit()

        # Dla każdego piątku
        for i, friday in enumerate(fridays):
            # Zasada "po Bożym Ciele" - 5 czerwca wypada piątek, przenosimy data_wykonania na 8 czerwca.
            if friday == date(2026, 6, 5):
                wykonanie_date = date(2026, 6, 8)
            else:
                wykonanie_date = friday
                
            # data_wykonania ustawiamy na np. godzine 09:00:00 rano
            dt_wykonanie = datetime.combine(wykonanie_date, datetime.min.time()) + timedelta(hours=9)
            
            # User na przemian
            user = users[i % 2]
            
            for linia in lines:
                cursor.execute(
                    """
                    INSERT INTO czyszczenie_separatorow 
                    (linia, data_planu, data_wykonania, login_wykonawcy, status, komentarz)
                    VALUES (%s, %s, %s, %s, 'completed', %s)
                    """,
                    (linia, friday, dt_wykonanie, user, "Wpis wprowadzony automatycznie na podstawie historii")
                )
        
        conn.commit()
        print(f"Dodano historyczne wpisy od 1 czerwca dla linii: {', '.join(lines)}.")
    except Exception as e:
        print(f"Błąd podczas wstawiania danych: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    generate_historical_separator_cleanings()
