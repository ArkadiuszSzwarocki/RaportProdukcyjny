"""
FolioService — Rozliczenie rolek folii dla AGRO Workowanie.

Obsługuje:
- Pobieranie aktywnych rolek podpiętych do zlecenia
- Zamykanie rolki przez operatora (z wyliczeniem strat)
- Automatyczne zamknięcie rolki (gdy zapełniona lista palet)
- Podsumowanie rolek dla zlecenia
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.db import get_db_connection, get_table_name


def _get_mqtt_counter() -> int:
    """Zwraca aktualny licznik MQTT lub 0 jeśli niedostępny."""
    try:
        from app.services.mqtt_service import get_latest_data
        return int(get_latest_data().get('counter', 0) or 0)
    except Exception:
        return 0


class FolioService:
    """Serwis zarządzania rolkami folii dla linii AGRO Workowanie."""

    # Dostępne lokalizacje zwrotu resztki rolki
    LOKALIZACJE_ZWROTU = ['MOP01', 'R06', 'Odpad'] + [f'R06{str(i+1).zfill(2)}01' for i in range(10)]

    @staticmethod
    def get_active_rolls(plan_id: int) -> list[dict]:
        """
        Zwraca listę aktywnych rolek podpiętych do zlecenia Workowanie.

        Każda rolka wzbogacona jest o:
        - live_zuzyte: zużycie z licznika MQTT (counter_current - licznik_start)
        - szacowane_pozostalo: stan_poczatkowy - live_zuzyte
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT ap.id AS link_id, ap.plan_id, ap.opakowanie_id,
                       ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                       ap.licznik_start,
                       o.nazwa, o.stan_magazynowy AS stan_na_maszynie,
                       o.lokalizacja
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.plan_id = %s AND ap.is_active = TRUE
                ORDER BY ap.created_at ASC
                """,
                (plan_id,)
            )
            rows = cursor.fetchall() or []

            current_counter = _get_mqtt_counter()

            result = []
            for r in rows:
                stan_poczatkowy = float(r.get('stan_poczatkowy') or 0)
                licznik_start = int(r.get('licznik_start') or 0)

                # Zużycie z licznika MQTT
                live_zuzyte = 0
                if current_counter >= 0 and licznik_start >= 0 and current_counter >= licznik_start:
                    live_zuzyte = current_counter - licznik_start

                szacowane_pozostalo = max(stan_poczatkowy - live_zuzyte, 0)

                result.append({
                    'link_id': r['link_id'],
                    'plan_id': r['plan_id'],
                    'opakowanie_id': r['opakowanie_id'],
                    'nazwa': r.get('nazwa') or '',
                    'lokalizacja': r.get('lokalizacja') or '',
                    'stan_poczatkowy': stan_poczatkowy,
                    'licznik_start': licznik_start,
                    'current_counter': current_counter,
                    'live_zuzyte': live_zuzyte,
                    'szacowane_pozostalo': szacowane_pozostalo,
                })
            return result
        finally:
            conn.close()

    @staticmethod
    def get_plan_folio_history(plan_id: int) -> list[dict]:
        """Zwraca historię wszystkich zdarzeń rolek dla zlecenia."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT r.id, r.typ_zdarzenia, r.opakowanie_nazwa,
                       r.stan_przed, r.zuzyte_worki, r.stan_po,
                       r.straty_worki, r.pozostalo_na_rolce,
                       r.lokalizacja_zwrotu, r.licznik_start, r.licznik_stop,
                       r.link_id, r.autor_login, r.created_at
                FROM agro_workowanie_rozliczenie r
                WHERE r.plan_id = %s
                ORDER BY r.created_at ASC
                """,
                (plan_id,)
            )
            return cursor.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def get_plan_folio_summary(plan_id: int) -> dict:
        """
        Zwraca podsumowanie rozliczenia folii dla zlecenia:
        suma pobranych, zużytych (licznik), strat, pozostałych.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN typ_zdarzenia='WSADZENIE' THEN stan_przed ELSE 0 END), 0) AS suma_pobranych,
                    COALESCE(SUM(CASE WHEN typ_zdarzenia='ZAMKNIECIE' THEN zuzyte_worki ELSE 0 END), 0) AS suma_zuzyto,
                    COALESCE(SUM(straty_worki), 0) AS suma_strat,
                    COALESCE(SUM(pozostalo_na_rolce), 0) AS suma_pozostalo
                FROM agro_workowanie_rozliczenie
                WHERE plan_id = %s
                """,
                (plan_id,)
            )
            row = cursor.fetchone() or {}
            return {
                'suma_pobranych': float(row.get('suma_pobranych') or 0),
                'suma_zuzyto': float(row.get('suma_zuzyto') or 0),
                'suma_strat': float(row.get('suma_strat') or 0),
                'suma_pozostalo': float(row.get('suma_pozostalo') or 0),
            }
        finally:
            conn.close()

    @staticmethod
    def close_roll(link_id: int, pozostalo_szt: float, user_login: str, custom_licznik_start=None, custom_licznik_stop=None) -> tuple[bool, str]:
        """
        Zamyka aktywną rolkę folii.
        - Zapisuje stan końcowy w `agro_plan_opakowania`.
        - Przywraca do magazynu `pozostalo_szt` (status: DO_ZWROTU).
        - Zapisuje log w `agro_workowanie_rozliczenie` jako 'ZAMKNIECIE'.
        - Zapisuje ruch magazynowy 'ZWROT_Z_PRODUKCJI'.
        """
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # 1. Pobierz dane podpięcia i rolki
            cursor.execute(
                """
                SELECT ap.plan_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.licznik_start,
                       o.nazwa AS opak_nazwa, o.stan_magazynowy AS stan_na_maszynie
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.id = %s AND ap.is_active = TRUE
                """,
                (link_id,)
            )
            link = cursor.fetchone()
            if not link:
                return False, 'Nie znaleziono aktywnego podpięcia rolki (link_id=%s).' % link_id

            plan_id = link['plan_id']
            opakowanie_id = link['opakowanie_id']
            opak_nazwa = link.get('opak_nazwa') or ''
            stan_poczatkowy = float(link.get('stan_poczatkowy') or 0)
            
            licznik_start = int(link.get('licznik_start') or 0)
            if custom_licznik_start is not None:
                licznik_start = custom_licznik_start
                
            pozostalo_szt = max(float(pozostalo_szt), 0)

            # 2. Pobierz aktualny licznik MQTT (stop)
            if custom_licznik_stop is not None:
                licznik_stop = custom_licznik_stop
            else:
                licznik_stop = _get_mqtt_counter()

            # 3. Wylicz zużycie z licznika i straty
            zuzyte_licznik = 0
            if licznik_stop >= 0 and licznik_start >= 0 and licznik_stop >= licznik_start:
                zuzyte_licznik = licznik_stop - licznik_start

            # Fizyczne zużycie folii (ile faktycznie zniknęło z rolki)
            fizycznie_zuzyto = stan_poczatkowy - pozostalo_szt
            
            # Straty = to co fizycznie zniknęło z rolki MINUS to co faktycznie maszyna wybiła na liczniku
            straty = max(fizycznie_zuzyto - zuzyte_licznik, 0)

            # 4. Pobierz metadane zlecenia
            cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
            p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}

            # 5. Zamknij link
            cursor.execute(
                "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                (pozostalo_szt, link_id)
            )

            # 6. Zaktualizuj stan na maszynie (pozostaje na Maszynie)
            if pozostalo_szt > 0:
                cursor.execute(
                    "UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = 'Maszyna', updated_at = NOW() WHERE id = %s",
                    (pozostalo_szt, opakowanie_id)
                )
            else:
                cursor.execute(
                    "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'ZUŻYTE', updated_at = NOW() WHERE id = %s",
                    (opakowanie_id,)
                )

            # 8. Ruch magazynowy: ODPIECIE_OD_ZLECENIA
            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            try:
                cursor.execute(
                    f"INSERT INTO {table_ruch} "
                    "(surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                    "VALUES (%s, 'ODPIECIE_OD_ZLECENIA', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                    (
                        opakowanie_id,
                        pozostalo_szt,
                        pozostalo_szt,
                        user_login,
                        f"Zamknięcie rolki (plan #{plan_id}), pozostawiono na: Maszyna",
                    )
                )
            except Exception as ruch_ex:
                print(f"[WARN] FolioService.close_roll: błąd zapisu ruchu: {ruch_ex}")

            # 9. Wpis do agro_workowanie_rozliczenie z typem ZAMKNIECIE
            cursor.execute(
                """
                INSERT INTO agro_workowanie_rozliczenie (
                    plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                    stan_przed, zuzyte_worki, stan_po,
                    straty_worki, pozostalo_na_rolce, lokalizacja_zwrotu,
                    licznik_start, licznik_stop,
                    typ_zdarzenia, link_id, autor_login
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ZAMKNIECIE', %s, %s)
                """,
                (
                    plan_id, p_meta['data_planu'], p_meta['produkt'],
                    opakowanie_id, opak_nazwa,
                    stan_poczatkowy, fizycznie_zuzyto, pozostalo_szt,
                    straty, pozostalo_szt, 'Maszyna' if pozostalo_szt > 0 else '',
                    licznik_start, licznik_stop,
                    link_id, user_login,
                )
            )

            # --- AUTO DRUKOWANIE ETYKIETY ZEBRA (ZAMKNIĘCIE ROLKI) ---
            if pozostalo_szt > 0:
                try:
                    # Szukamy domyślnej drukarki (Zebra)
                    cursor.execute("SELECT ip, nazwa FROM drukarki WHERE aktywna = 1 AND nazwa LIKE %s LIMIT 1", ('%Zebra%',))
                    printer = cursor.fetchone()
                    if not printer:
                        # Fallback do jakiejkolwiek aktywnej drukarki etykiet
                        cursor.execute("SELECT ip, nazwa FROM drukarki WHERE aktywna = 1 LIMIT 1")
                        printer = cursor.fetchone()

                    if printer:
                        # Pobieramy dane rolki
                        cursor.execute("SELECT nr_palety, nr_partii, data_produkcji, data_przydatnosci FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
                        rolka_dane = cursor.fetchone()

                        if rolka_dane:
                            import threading
                            import requests
                            import urllib3
                            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                            payload = {
                                "drukarka": printer['nazwa'],
                                "ip": printer['ip'],
                                "typ": "opakowanie",
                                "dane": {
                                    "palletData": {
                                        "nrPalety": rolka_dane.get('nr_palety') or '---',
                                        "productName": opak_nazwa,
                                        "batchNumber": rolka_dane.get('nr_partii') or '---',
                                        "productionDate": str(rolka_dane.get('data_produkcji')) if rolka_dane.get('data_produkcji') else '---',
                                        "expiryDate": str(rolka_dane.get('data_przydatnosci')) if rolka_dane.get('data_przydatnosci') else '---',
                                        "currentWeight": float(pozostalo_szt),
                                        "unit": "szt.",
                                        "labNotes": f"ZAMKNIĘTO ROLKĘ"
                                    }
                                }
                            }

                            def run_print():
                                url = "http://127.0.0.1:3001/drukuj-zpl"
                                for _ in range(2):
                                    try:
                                        requests.post(url, json=payload, verify=False, timeout=3)
                                    except Exception:
                                        pass

                            threading.Thread(target=run_print, daemon=True).start()
                            print(f"[FolioService] Automatyczny wydruk etykiety dla rolki {opak_nazwa} na drukarkę {printer['nazwa']}")
                except Exception as print_ex:
                    print(f"[FolioService] Błąd automatycznego druku po zamknięciu rolki: {print_ex}")

            conn.commit()
            return True, None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def get_live_status(plan_id: int) -> dict:
        """
        Zwraca live status dla widoku AJAX:
        aktywne rolki + aktualny licznik MQTT.
        """
        rolls = FolioService.get_active_rolls(plan_id)
        current_counter = _get_mqtt_counter()
        return {
            'current_counter': current_counter,
            'active_rolls': rolls,
        }

    @staticmethod
    def undo_close_roll(rozliczenie_id: int, user_login: str) -> tuple[bool, str | None]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, plan_id, opakowanie_id, straty_worki, link_id, pozostalo_na_rolce
                FROM agro_workowanie_rozliczenie 
                WHERE id = %s AND typ_zdarzenia = 'ZAMKNIECIE'
            """, (rozliczenie_id,))
            roz = cursor.fetchone()
            if not roz:
                return False, 'Nie znaleziono zamknięcia (lub wpis nie jest typu ZAMKNIĘCIE).'

            plan_id = roz['plan_id']
            opak_id = roz['opakowanie_id']
            link_id = roz['link_id']
            straty = float(roz['straty_worki'] or 0)

            # Re-activate the roll link
            if link_id:
                cursor.execute(
                    "UPDATE agro_plan_opakowania SET is_active = TRUE, stan_koncowy = NULL WHERE id = %s",
                    (link_id,)
                )

            # Bring it back to Maszyna
            cursor.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'Maszyna', updated_at = NOW() WHERE id = %s",
                (opak_id,)
            )

            # Subtract from defective bags if needed
            if straty > 0:
                cursor.execute(
                    "UPDATE plan_produkcji_agro SET uszkodzone_worki = GREATEST(COALESCE(uszkodzone_worki, 0) - %s, 0) WHERE id = %s",
                    (int(straty), plan_id)
                )

            # Delete the movement log
            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            cursor.execute(f"""
                DELETE FROM {table_ruch}
                WHERE surowiec_id = %s AND typ_ruchu = 'ZWROT_Z_PRODUKCJI'
                ORDER BY id DESC LIMIT 1
            """, (opak_id,))

            # Delete the history row
            cursor.execute("DELETE FROM agro_workowanie_rozliczenie WHERE id = %s", (rozliczenie_id,))

            conn.commit()
            return True, None
        except Exception as e:
            try: conn.rollback()
            except: pass
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def edit_active_roll(link_id: int, new_amount: float, user_login: str) -> tuple[bool, str | None]:
        """Korekta ilości pobranej (wsadzenia) dla aktywnej rolki na maszynie."""
        if new_amount <= 0:
            return False, "Ilość musi być większa od zera."

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # Find the active roll link
            cursor.execute("SELECT plan_id, opakowanie_id, stan_poczatkowy FROM agro_plan_opakowania WHERE id = %s AND is_active = TRUE", (link_id,))
            link = cursor.fetchone()
            if not link:
                return False, "Nie znaleziono aktywnego podpięcia na maszynie."

            opakowanie_id = link['opakowanie_id']
            old_amount = float(link['stan_poczatkowy'] or 0)
            diff = new_amount - old_amount

            if diff == 0:
                return True, None

            # Check warehouse if diff > 0
            if diff > 0:
                cursor.execute("SELECT stan_magazynowy FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
                magazyn = cursor.fetchone()
                if not magazyn or float(magazyn['stan_magazynowy'] or 0) < diff:
                    return False, f"Brak wystarczającej ilości w magazynie do pobrania dodatkowych {diff} szt."

            # Update link
            cursor.execute("UPDATE agro_plan_opakowania SET stan_poczatkowy = %s WHERE id = %s", (new_amount, link_id))

            # Update history row 'WSADZENIE'
            cursor.execute("""
                UPDATE agro_workowanie_rozliczenie 
                SET stan_przed = %s 
                WHERE link_id = %s AND typ_zdarzenia = 'WSADZENIE'
            """, (new_amount, link_id))

            # Update warehouse
            cursor.execute("""
                UPDATE magazyn_opakowania 
                SET stan_magazynowy = stan_magazynowy - %s, updated_at = NOW() 
                WHERE id = %s
            """, (diff, opakowanie_id))

            # Add movement
            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            cursor.execute(f"""
                INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, status, autor_login, autor_data, komentarz)
                VALUES (%s, 'KOREKTA', %s, 'POTWIERDZONE', %s, NOW(), %s)
            """, (opakowanie_id, diff, user_login, f"Korekta wsadu rolki z {old_amount} na {new_amount} (różnica: {diff} szt.)"))

            conn.commit()
            return True, None
        except Exception as e:
            try: conn.rollback()
            except: pass
            return False, str(e)
        finally:
            conn.close()
