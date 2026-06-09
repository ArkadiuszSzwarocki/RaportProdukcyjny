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
                if current_counter > 0 and licznik_start > 0 and current_counter > licznik_start:
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
                       r.autor_login, r.created_at
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
    def close_roll(
        link_id: int,
        pozostalo_szt: float,
        lokalizacja_zwrotu: str,
        user_login: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Zamknięcie rolki przez operatora.

        Args:
            link_id: ID rekordu agro_plan_opakowania
            pozostalo_szt: Ile sztuk zostało na rolce (wpisane przez operatora)
            lokalizacja_zwrotu: Lokalizacja do której trafi reszta (np. 'Magazyn folie')
            user_login: Login operatora

        Returns:
            (success: bool, error_message: str | None)
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Pobierz dane linku
            cursor.execute(
                """
                SELECT ap.id, ap.plan_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.licznik_start,
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
            pozostalo_szt = max(float(pozostalo_szt), 0)

            # 2. Pobierz aktualny licznik MQTT (stop)
            licznik_stop = _get_mqtt_counter()

            # 3. Wylicz zużycie z licznika i straty
            zuzyte_licznik = 0
            if licznik_stop > 0 and licznik_start > 0 and licznik_stop > licznik_start:
                zuzyte_licznik = licznik_stop - licznik_start

            # Straty = pobranych - zużyto_licznikiem - pozostało
            straty = max(stan_poczatkowy - zuzyte_licznik - pozostalo_szt, 0)

            # 4. Pobierz metadane zlecenia
            cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
            p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}

            # 5. Zamknij link
            cursor.execute(
                "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                (pozostalo_szt, link_id)
            )

            # 6. Zeruj stan na maszynie (rolka opuszcza maszynę)
            cursor.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'ZUŻYTE' WHERE id = %s",
                (opakowanie_id,)
            )

            # 7. Jeśli zostało coś na rolce — zwróć do magazynu
            if pozostalo_szt > 0 and lokalizacja_zwrotu and lokalizacja_zwrotu.strip():
                # Sprawdź czy jest już wpis dla tej samej nazwy i lokalizacji
                cursor.execute(
                    "SELECT id, stan_magazynowy FROM magazyn_opakowania WHERE nazwa = %s AND lokalizacja = %s LIMIT 1",
                    (opak_nazwa, lokalizacja_zwrotu)
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = stan_magazynowy + %s, updated_at = NOW() WHERE id = %s",
                        (pozostalo_szt, existing['id'])
                    )
                else:
                    cursor.execute(
                        "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                        (opak_nazwa, pozostalo_szt, lokalizacja_zwrotu)
                    )

            # 8. Ruch magazynowy: ZWROT_Z_PRODUKCJI
            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            try:
                cursor.execute(
                    f"INSERT INTO {table_ruch} "
                    "(surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                    "VALUES (%s, 'ZWROT_Z_PRODUKCJI', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                    (
                        opakowanie_id,
                        pozostalo_szt,
                        pozostalo_szt,
                        user_login,
                        f"Zamknięcie rolki (plan #{plan_id}), zwrot na: {lokalizacja_zwrotu or 'brak'}",
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
                    stan_poczatkowy, zuzyte_licznik, pozostalo_szt,
                    straty, pozostalo_szt, lokalizacja_zwrotu or '',
                    licznik_start, licznik_stop,
                    link_id, user_login,
                )
            )

            # 10. Zaktualizuj uszkodzone_worki w planie AGRO
            try:
                cursor.execute(
                    "UPDATE plan_produkcji_agro SET uszkodzone_worki = COALESCE(uszkodzone_worki, 0) + %s WHERE id = %s",
                    (int(straty), plan_id)
                )
            except Exception:
                pass

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
