"""
Automatycznie wydzielone production_repository.
"""
import mysql.connector
from app.config import DB_CONFIG, BUFOR_LOOKBACK_DAYS, BUFOR_LOOKAHEAD_DAYS
import os
from werkzeug.security import generate_password_hash
import time
import threading
from datetime import date, timedelta
import uuid
from app.db_tables import resolve_table_name
from app.core.database import get_db_connection, get_table_name

def refresh_bufor_queue(conn=None, linia='PSD'):
    """Odświeța bufor - dodaje nowe zlecenia z przepisanymi kolejkami (OPTIMIZED)"""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    linia = (linia or 'PSD').upper()
    table_plan = get_table_name('plan_produkcji', linia)
    table_palety = get_table_name('palety_workowanie', linia)
    table_bufor = get_table_name('bufor', linia)

    try:
        cursor = conn.cursor()
        today = date.today()
        # Zakres dat używany przy odświeżaniu bufora - stała konfiguracja z app.config
        start_date = today - timedelta(days=BUFOR_LOOKBACK_DAYS)
        end_date = today + timedelta(days=BUFOR_LOOKAHEAD_DAYS)

        # SYNC 1: Synchronizuj Workowanie.tonaz = Zasyp.tonaz_rzeczywisty
        try:
            cursor.execute(f"""
                UPDATE {table_plan} w
                JOIN {table_plan} z ON z.id = w.zasyp_id
                SET w.tonaz = COALESCE(z.tonaz_rzeczywisty, 0)
                WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND z.sekcja = 'Zasyp'
                  AND COALESCE(z.tonaz_rzeczywisty, 0) > 0
                  AND COALESCE(w.tonaz, 0) = 0
                  AND w.data_planu >= %s AND w.data_planu <= %s
            """, (start_date, end_date))
            if cursor.rowcount > 0:
                print(f"[SYNC-{linia}] Workowanie.tonaz synchronized: {cursor.rowcount} rows")
        except Exception as e:
            print(f"[WARN] Sync Workowanie.tonaz failed ({linia}): {e}")

        # SYNC 2: Synchronizuj Workowanie.tonaz_rzeczywisty = sum palet
        try:
            cursor.execute(f"""
                UPDATE {table_plan} w
                SET w.tonaz_rzeczywisty = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM {table_palety} pw
                    WHERE pw.plan_id = w.id
                )
                WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND w.data_planu >= %s AND w.data_planu <= %s
            """, (start_date, end_date))
            if cursor.rowcount > 0:
                print(f"[SYNC-{linia}] Workowanie.tonaz_rzeczywisty synchronized: {cursor.rowcount} rows")
        except Exception as e:
            print(f"[WARN] Sync Workowanie.tonaz_rzeczywisty failed ({linia}): {e}")

        # 1. Oznacz wpisy z bufora jako 'zamkniete' gdy nie ma aktywnego Workowania
        #    i nic do rozliczenia (tonaz_rzeczywisty - spakowano <= 0).
        cursor.execute(f"""
            UPDATE {table_bufor}
            SET status = 'zamkniete'
            WHERE status = 'aktywny'
              AND NOT EXISTS (
                  SELECT 1 FROM {table_plan} w
                  WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND w.status IN ('w toku', 'zaplanowane')
                    AND w.produkt = {table_bufor}.produkt AND w.data_planu = {table_bufor}.data_planu
              )
              AND COALESCE({table_bufor}.tonaz_rzeczywisty, 0) - COALESCE({table_bufor}.spakowano, 0) <= 0
        """)
        updated = cursor.rowcount

        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            SET b.status = 'zamkniete'
            WHERE b.status = 'aktywny'
              AND z.sekcja = 'Zasyp'
              AND z.real_start IS NULL
              AND z.typ_zlecenia != 'carry_over_ghost'
        """)
        if cursor.rowcount > 0:
            print(f"[CLEANUP-{linia}] Zamknięto {cursor.rowcount} wpisów bufora z Zasypem bez real_start")

        # 1d. Re-otwórz wpisy bufora dla ghost Zasypów (carry-over/przeniesione), które zostały
        #     błędnie zamknięte, gdy Workowanie jest nadal zaplanowane.
        #     Ghost Zasyp ma teraz status='zaplanowane' (nie 'zakonczone'), sprawdzamy przez typ_zlecenia.
        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            SET b.status = 'aktywny'
            WHERE b.status = 'zamkniete'
              AND z.sekcja = 'Zasyp'
              AND z.typ_zlecenia = 'carry_over_ghost'
              AND EXISTS (
                  SELECT 1 FROM {table_plan} w
                  WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND w.status IN ('w toku', 'zaplanowane')
                    AND w.produkt = b.produkt AND w.data_planu = b.data_planu
              )
        """)
        if cursor.rowcount > 0:
            print(f"[CLEANUP-{linia}] Re-otwarto {cursor.rowcount} wpisów bufora dla ghost Zasypów (carry-over)")

        # 1c. Zamknij osierocone wpisy bufora (zasyp_id wskazuje na nieistniejący plan).
        cursor.execute(f"""
            UPDATE {table_bufor} b
            SET b.status = 'zamkniete'
            WHERE b.status = 'aktywny'
              AND NOT EXISTS (
                  SELECT 1 FROM {table_plan} z WHERE z.id = b.zasyp_id
              )
        """)
        if cursor.rowcount > 0:
            print(f"[CLEANUP-{linia}] Zamknięto {cursor.rowcount} wpisów bufora z Zasypem bez real_start")

        # 2. Pobierz Zasypy dla skonfigurowanego zakresu dat.
        #    ZASADA: do bufora trafia zasyp dopiero gdy pojawi się na zasypie (real_start IS NOT NULL).
        #    Statusy 'w toku' i 'zakonczone' oznaczają, że zasyp faktycznie wystartował.
        #    Zasypy 'zaplanowane' (bez real_start) NIE trafiają do bufora — kolejkowanie
        #    zaczyna się dopiero gdy zlecenie pojawi się fizycznie na zasypie.
        cursor.execute(f"""
            SELECT z.id, z.data_planu, z.produkt, z.nazwa_zlecenia, z.typ_produkcji,
                   COALESCE(NULLIF(z.tonaz_rzeczywisty, 0), z.tonaz) AS efektywny_tonaz,
                   z.status
            FROM {table_plan} z
            INNER JOIN {table_plan} w ON w.zasyp_id = z.id
            WHERE z.sekcja = 'Zasyp' AND w.sekcja IN ('Workowanie', 'Czyszczenie')
              AND w.status IN ('w toku', 'zaplanowane')
              AND (
                  -- Normalne Zasypy: muszą mieć real_start i status 'w toku' lub 'zakonczone'
                  (z.status IN ('w toku', 'zakonczone') AND z.real_start IS NOT NULL)
                  OR
                  -- Ghost Zasypy (carry-over): zaplanowane, brak real_start, ale mają tonaz w zleceniu Workowanie
                  (z.typ_zlecenia = 'carry_over_ghost' AND z.status = 'zaplanowane')
              )
              AND z.data_planu >= %s AND z.data_planu <= %s
              AND COALESCE(NULLIF(w.tonaz, 0), 0) > 0
            ORDER BY z.data_planu DESC, COALESCE(z.real_start, '00:00:00') ASC, z.id ASC
        """, (start_date, end_date))

        zasypy_do_bufora = cursor.fetchall()

        # 3. Dodaj brakujące Zasypy do bufora
        added = 0
        for z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_status in zasypy_do_bufora:
            cursor.execute(
                f"SELECT id FROM {table_bufor} WHERE zasyp_id = %s AND status = 'aktywny'",
                (z_id,)
            )
            if cursor.fetchone():
                continue

            # Pobierz max kolejkę (po WSZYSTKICH statusach — unique key jest globalna) i ilość spakowanego
            cursor.execute(f"""
                SELECT COALESCE(MAX(b.kolejka), 0), COALESCE(SUM(pw.waga), 0)
                FROM {table_bufor} b
                LEFT JOIN {table_palety} pw ON pw.plan_id IN (
                    SELECT id FROM {table_plan}
                    WHERE data_planu = %s AND produkt = %s AND sekcja IN ('Workowanie', 'Czyszczenie')
                )
                WHERE b.data_planu = %s AND b.produkt = %s
            """, (z_data, z_produkt, z_data, z_produkt))

            result = cursor.fetchone()
            next_kolejka = (result[0] or 0) + 1
            spakowano = result[1] or 0

            # Sprawdź, czy dla tej daty/produktu/kolejki już istnieje wpis (dowolny status)
            cursor.execute(
                f"SELECT id FROM {table_bufor} WHERE data_planu = %s AND produkt = %s AND kolejka = %s",
                (z_data, z_produkt, next_kolejka)
            )
            if cursor.fetchone():
                continue

            # Dodaj do bufora
            cursor.execute(f"""
                INSERT INTO {table_bufor}
                (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji,
                 tonaz_rzeczywisty, spakowano, kolejka, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'aktywny')
            """, (z_id, z_data, z_produkt, z_nazwa or '', z_typ or 'worki_zgrzewane_25',
                  z_tonaz, spakowano, next_kolejka))
            if cursor.rowcount:
                added += 1

        # 4. Renumeruj kolejki (dwustopniowo — unikamy konfliktu z wpisami 'zamkniete')
        #
        # Problem: ROW_NUMBER zaczyna od 1, ale wpisy 'zamkniete' mogą zajmować niskie numery
        # dla tego samego (data_planu, produkt). Bezpośrednia UPDATE-a powoduje Duplicate Key.
        #
        # Rozwiązanie:
        #   Krok 4a — przesuń wszystkie aktywne do strefy tymczasowej (ujemne -id, gwarantowanie unikalne).
        #   Krok 4b — przypisz właściwe numery startujące od MAX(zamkniete)+1 (globalnie na datę),
        #             posortowane wg real_start zasypu (CASE WHEN, bo MySQL NULL < wartości w ASC).

        cursor.execute(f"""
            UPDATE {table_bufor}
            SET kolejka = -id
            WHERE status = 'aktywny'
              AND data_planu >= %s AND data_planu <= %s
        """, (start_date, end_date))

        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN (
                SELECT b2.id,
                       (SELECT COALESCE(MAX(b3.kolejka), 0)
                        FROM {table_bufor} b3
                        WHERE b3.data_planu = b2.data_planu
                          AND b3.status != 'aktywny')
                       + ROW_NUMBER() OVER (
                           PARTITION BY b2.data_planu
                           ORDER BY b2.data_planu DESC,
                                    CASE WHEN (SELECT z.real_start FROM {table_plan} z WHERE z.id = b2.zasyp_id) IS NOT NULL THEN 0 ELSE 1 END ASC,
                                    COALESCE((SELECT z.real_start FROM {table_plan} z WHERE z.id = b2.zasyp_id), '9999-12-31 23:59:59') ASC,
                                    b2.id ASC
                       ) AS nowa_kolejka
                FROM {table_bufor} b2
                WHERE b2.status = 'aktywny'
            ) ranked ON b.id = ranked.id
            SET b.kolejka = ranked.nowa_kolejka
        """)

        # 5. Aktualizuj tonaz_rzeczywisty i spakowano w jednym UPDATE
        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            SET b.tonaz_rzeczywisty = COALESCE(z.tonaz_rzeczywisty, 0),
                b.spakowano = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM {table_palety} pw
                    INNER JOIN {table_plan} w ON pw.plan_id = w.id
                    WHERE w.data_planu = b.data_planu AND w.produkt = b.produkt
                      AND w.sekcja IN ('Workowanie', 'Czyszczenie')
                )
            WHERE b.status = 'aktywny'
              AND COALESCE(z.tonaz_rzeczywisty, 0) > 0
              AND COALESCE(z.typ_zlecenia, '') != 'carry_over_ghost'
        """)

        # 5b. Dla ghost Zasypów (carry_over_ghost): tonaz_rzeczywisty bufora bierzemy z Workowanie.tonaz
        #     bo Zasyp ghost ma tonaz_rzeczywisty=0 (nie był fizycznie sypany)
        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            JOIN {table_plan} w ON w.zasyp_id = z.id AND w.sekcja IN ('Workowanie', 'Czyszczenie')
            SET b.tonaz_rzeczywisty = COALESCE(w.tonaz, 0),
                b.spakowano = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM {table_palety} pw
                    WHERE pw.plan_id = w.id
                )
            WHERE b.status = 'aktywny'
              AND z.typ_zlecenia = 'carry_over_ghost'
              AND z.sekcja = 'Zasyp'
              AND COALESCE(w.tonaz, 0) > 0
        """)

        conn.commit()
        print(f"[BUFOR-{linia}] Refreshed buffer: marked_closed {updated}, added {added}")
        
    except Exception as e:
        print(f"[ERROR] refresh_bufor_queue: {e}")
        conn.rollback()
        raise
    finally:
        if close_conn:
            cursor.close()
            conn.close()

def _auto_confirm_existing_palety(cursor):
    """Auto-confirm all existing palety with data_dodania and set confirmation time to +2 minutes."""
    try:
        # Update all palety that have data_dodania but haven't been confirmed yet
        # Set: status='przyjeta', czas_rzeczywistego_potwierdzenia = TIME(data_dodania + 2 min), data_potwierdzenia=NOW()
        cursor.execute("""
            UPDATE palety_workowanie 
            SET 
                status = 'przyjeta',
                czas_rzeczywistego_potwierdzenia = TIME(DATE_ADD(data_dodania, INTERVAL 2 MINUTE)),
                data_potwierdzenia = NOW(),
                czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW())
            WHERE 
                data_dodania IS NOT NULL 
                AND (status IS NULL OR status = 'do_przyjecia' OR czas_rzeczywistego_potwierdzenia IS NULL)
        """)
        affected = cursor.rowcount
        if affected > 0:
            print(f"[OK] Auto-confirmed {affected} existing palety (set confirmation time to +2 min)")
    except Exception as e:
        print(f"[INFO] Auto-confirm migration skipped or already applied: {e}")

def rollover_unfinished(from_date, to_date):
    """Przenosi niezakończone zlecenia z `from_date` na `to_date`.
    Zlecenia przenoszone są jako nowe wiersze z datą docelową, statusem
    'zaplanowane' (reset real_start/real_stop) i odpowiednią kolejnością.
            # Ensure a uniqueness constraint to prevent multiple Workowanie rows pointing to the same zasyp_id
            try:
                cursor.execute("SHOW INDEX FROM plan_produkcji WHERE Key_name = 'uq_plan_produkcji_zasyp_sekcja'")
                if not cursor.fetchone():
                    try:
                        cursor.execute("ALTER TABLE plan_produkcji ADD UNIQUE INDEX uq_plan_produkcji_zasyp_sekcja (zasyp_id, sekcja)")
                    except Exception:
                        # If index creation fails (e.g., existing conflicting data), skip — migration scripts handle deduplication separately
                        pass
            except Exception:
                pass
    Oryginały są usuwane.
    Zwraca liczbę przeniesionych zleceń.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sekcja, produkt, tonaz, status, typ_produkcji, nazwa_zlecenia, typ_zlecenia, nr_receptury FROM plan_produkcji WHERE data_planu=%s", (from_date,))
        rows = cursor.fetchall()
        moved = 0
        moved_ids = []
        for row in rows:
            pid, sekcja, produkt, tonaz, status, typ_produkcji, nazwa_zlecenia, typ_zlecenia, nr_receptury = row
            if status == 'zakonczone':
                continue

            # pobierz kolejność docelową
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (to_date,))
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1

            cursor.execute(
                "INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, kolejnosc, typ_produkcji, nazwa_zlecenia, typ_zlecenia, nr_receptury) VALUES (%s, %s, %s, %s, 'zaplanowane', NULL, NULL, NULL, %s, %s, %s, %s, %s)",
                (to_date, sekcja, produkt, tonaz, nk, typ_produkcji or 'worki_zgrzewane_25', nazwa_zlecenia or '', typ_zlecenia or '', nr_receptury or '')
            )
            # usuń oryginał
            cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (pid,))
            moved += 1
            moved_ids.append(pid)
            try:
                print(f"[rollover] Przeniesiono id={pid} produkt={produkt} sekcja={sekcja} tonaz={tonaz}")
            except Exception:
                # ensure logging doesn't break rollover
                pass

        conn.commit()
        try:
            if moved_ids:
                print(f"[rollover] Podsumowanie: przeniesiono {moved} zlecen: {', '.join(str(i) for i in moved_ids)}")
            else:
                print("[rollover] Podsumowanie: brak zlecen do przeniesienia.")
        except Exception:
            pass
        return moved

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[ERROR] rollover_unfinished failed: {e}")
        return 0
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def log_plan_history(plan_id, action, changes, user_login=None):
    """Zapisuje wpis do tabeli `plan_history`.
    `changes` może być stringiem (np. JSON) opisującym co się zmieniło.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO plan_history (plan_id, action, changes, user_login) VALUES (%s, %s, %s, %s)", (plan_id, action, changes, user_login))
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
    except Exception:
        try:
            conn.close()
        except Exception:
            pass

def insert_dosypka(plan_id, nazwa, kg, pracownik_id=None):
    """Insert single dosypka record."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dosypki (plan_id, nazwa, kg, pracownik_id, potwierdzone) VALUES (%s, %s, %s, %s, 0)",
            (plan_id, nazwa, kg, pracownik_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False

def list_unconfirmed_dosypki(linia='PSD'):
    """Return list of active unconfirmed dosypki."""
    try:
        table_dosypki = get_table_name('dosypki', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, plan_id, nazwa, kg, data_zlecenia, pracownik_id,
                   COALESCE(anulowana, 0), anulowal_login, data_anulowania
            FROM {table_dosypki}
            WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
            ORDER BY data_zlecenia ASC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []

def confirm_dosypka(dosypka_id, potwierdzil_pracownik_id=None, linia='PSD'):
    """Mark dosypka as confirmed (odczytanie) and sync plan's tonaz_rzeczywisty."""
    try:
        table_dosypki = get_table_name('dosypki', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_szarze = get_table_name('szarze', linia)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get plan_id first
        cursor.execute(f"SELECT plan_id FROM {table_dosypki} WHERE id=%s", (dosypka_id,))
        row = cursor.fetchone()
        plan_id = row[0] if row else None
        
        # Update dosypka status
        cursor.execute(f"UPDATE {table_dosypki} SET potwierdzone=1, potwierdzil_pracownik_id=%s, data_potwierdzenia=NOW() WHERE id=%s", (potwierdzil_pracownik_id, dosypka_id))
        
        # Synchronize plan's tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki potwierdzone)
        if plan_id:
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                f"WHERE id = %s",
                (plan_id, plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False

