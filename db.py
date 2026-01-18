import mysql.connector
import logging  # <--- NOWE: Dodaj ten import
from config import DB_CONFIG

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG, buffered=True)

def setup_database():
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        
        # ... (Tu są Twoje polecenia CREATE TABLE - zostaw je bez zmian) ...
        # (Dla przejrzystości pominąłem środek funkcji, bo jest długi)
        
        # Migracje...
        try: cursor.execute("ALTER TABLE dziennik_zmiany ADD COLUMN kategoria VARCHAR(50) NULL")
        except: pass
        # ... (reszta migracji) ...

        conn.commit(); conn.close()
    except Exception as e:
        # KROK 4: Zamiast print(), zapisujemy błąd do pliku
        logging.error(f"KRYTYCZNY BŁĄD BAZY DANYCH: {e}") 
        # print(f"Błąd bazy: {e}") # To możemy zakomentować lub usunąć


def rollover_unfinished(from_date, to_date):
    """Przenosi niezakończone zlecenia z from_date na to_date.

    Mechanizm: kopiujemy wiersze z plan_produkcji, które mają status != 'zakonczone'
    i zaplanowaną datę = from_date. Przy kopiowaniu unikamy duplikatów —
    jeżeli dla tej samej kombinacji sekcja/produkt/tonaz istnieje już rekord
    na to_date, kopiowanie jest pomijane.

    Zwraca liczbę dodanych wierszy.
    """
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status)
            SELECT %s, p.sekcja, p.produkt, p.tonaz, 'zaplanowane'
            FROM plan_produkcji p
            WHERE p.data_planu = %s AND COALESCE(p.status, '') != 'zakonczone'
              AND NOT EXISTS (
                SELECT 1 FROM plan_produkcji p2
                WHERE p2.data_planu = %s
                  AND p2.sekcja = p.sekcja
                  AND p2.produkt = p.produkt
                  AND (p2.tonaz = p.tonaz OR (p2.tonaz IS NULL AND p.tonaz IS NULL))
              )
        """, (to_date, from_date, to_date))
        added = cur.rowcount
        conn.commit(); conn.close()
        return added
    except Exception as e:
        print(f"Błąd przy rollover: {e}")
        try:
            conn.close()
        except:
            pass
        return 0