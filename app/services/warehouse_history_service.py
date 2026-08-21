"""
WarehouseHistoryService — centralny serwis historii ruchów magazynowych i produkcyjnych.
Konsoliduje logowanie zdarzeń oraz odpytywanie historii (stacje zasypowe, przesunięcia regałowe,
wydania, zużycia i archiwizacje) dla linii PSD, AGRO oraz widoku ALL.
"""

from datetime import datetime
from app.db import get_db_connection, get_table_name


class WarehouseHistoryService:
    @staticmethod
    def record_movement(
        paleta_id: int | None,
        linia: str,
        typ_palety: str,
        akcja: str,
        lokalizacja_zrodlowa: str | None,
        lokalizacja_docelowa: str | None,
        komentarz: str | None,
        user_login: str | None = 'System'
    ) -> bool:
        """
        Zapisuje ruch palety/surowca w centralnej tabeli `palety_historia`.
        """
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO palety_historia (
                    paleta_id, linia, typ_palety, akcja, 
                    lokalizacja_zrodlowa, lokalizacja_docelowa, 
                    komentarz, user_login, data_ruchu
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                paleta_id,
                (linia or 'PSD').upper(),
                (typ_palety or 'surowiec').lower(),
                (akcja or 'PRZESUNIECIE').upper(),
                lokalizacja_zrodlowa,
                lokalizacja_docelowa,
                komentarz,
                user_login or 'System',
                datetime.now()
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[WarehouseHistoryService] Błąd zapisu ruchu: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def get_unified_station_and_movement_history(
        linia: str = 'ALL',
        data_od: str | None = None,
        data_do: str | None = None,
        surowiec: str | None = None,
        stacja: str | None = None,
        limit: int = 500
    ) -> list[dict]:
        """
        Zwraca skonsolidowaną historię ruchów magazynowych i stacji produkcyjnych
        łącząc dane z tabeli `palety_historia` oraz legacy `magazyn_ruch` / `magazyn_agro_ruch`.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Filtry dat i tekstu
            date_cond_ph = ""
            date_cond_psd = ""
            date_cond_agro = ""
            date_params_ph = []
            date_params_psd = []
            date_params_agro = []

            if data_od:
                date_cond_ph += " AND ph.data_ruchu >= %s"
                date_params_ph.append(f"{data_od} 00:00:00")
                date_cond_psd += " AND r.created_at >= %s"
                date_params_psd.append(f"{data_od} 00:00:00")
                date_cond_agro += " AND r.autor_data >= %s"
                date_params_agro.append(f"{data_od} 00:00:00")

            if data_do:
                date_cond_ph += " AND ph.data_ruchu <= %s"
                date_params_ph.append(f"{data_do} 23:59:59")
                date_cond_psd += " AND r.created_at <= %s"
                date_params_psd.append(f"{data_do} 23:59:59")
                date_cond_agro += " AND r.autor_data <= %s"
                date_params_agro.append(f"{data_do} 23:59:59")

            line_cond_ph = ""
            line_params_ph = []
            if linia and linia != 'ALL':
                line_cond_ph = " AND ph.linia = %s"
                line_params_ph = [linia]

            stacja_cond_ph = ""
            stacja_params_ph = []
            stacja_cond_legacy = ""
            stacja_params_legacy = []

            if stacja:
                stacja_cond_ph = " AND (ph.lokalizacja_docelowa LIKE %s OR ph.lokalizacja_zrodlowa LIKE %s OR ph.komentarz LIKE %s)"
                stacja_params_ph = [f"%{stacja}%", f"%{stacja}%", f"%{stacja}%"]
                stacja_cond_legacy = " AND (r.zbiornik LIKE %s OR r.lokalizacja LIKE %s OR r.komentarz LIKE %s)"
                stacja_params_legacy = [f"%{stacja}%", f"%{stacja}%", f"%{stacja}%"]
            else:
                # Domyślny filtr dla stanowisk / ruchów
                stacja_cond_ph = ""
                stacja_cond_legacy = " AND (r.lokalizacja LIKE 'BB%%' OR r.lokalizacja LIKE 'MZ%%' OR r.lokalizacja LIKE 'WZ%%' OR r.lokalizacja LIKE 'KO%%' OR r.lokalizacja LIKE 'ZB%%' OR r.lokalizacja LIKE 'MIX%%' OR r.zbiornik LIKE 'BB%%' OR r.zbiornik LIKE 'MZ%%' OR r.zbiornik LIKE 'WZ%%' OR r.zbiornik LIKE 'KO%%' OR r.zbiornik LIKE 'ZB%%' OR r.zbiornik LIKE 'MIX%%' OR r.komentarz LIKE '%do BB%' OR r.komentarz LIKE '%do MZ%' OR r.komentarz LIKE '%do WZ%' OR r.komentarz LIKE '%do KO%' OR r.komentarz LIKE '%do ZB%' OR r.komentarz LIKE '%do MIX%' OR r.komentarz LIKE '%-> BB%' OR r.komentarz LIKE '%-> MZ%' OR r.komentarz LIKE '%-> WZ%' OR r.komentarz LIKE '%-> KO%' OR r.komentarz LIKE '%-> ZB%' OR r.komentarz LIKE '%-> MIX%')"

            sur_cond_ph = ""
            sur_params_ph = []
            sur_cond_legacy = ""
            sur_params_legacy = []
            if surowiec:
                sur_cond_ph = " AND (sur.nazwa LIKE %s OR sur.nr_palety LIKE %s OR ph.komentarz LIKE %s)"
                sur_params_ph = [f"%{surowiec}%", f"%{surowiec}%", f"%{surowiec}%"]
                sur_cond_legacy = " AND (r.surowiec_nazwa LIKE %s OR pal.nazwa LIKE %s OR pal.nr_palety LIKE %s OR r.komentarz LIKE %s)"
                sur_params_legacy = [f"%{surowiec}%", f"%{surowiec}%", f"%{surowiec}%", f"%{surowiec}%"]

            # 1. Pobierz z palety_historia
            query_ph = f"""
                SELECT 
                    ph.id, 
                    ph.paleta_id,
                    ph.linia as linia_ruch,
                    ph.typ_palety,
                    ph.akcja as typ_ruchu,
                    ph.lokalizacja_zrodlowa,
                    ph.lokalizacja_docelowa,
                    ph.komentarz,
                    ph.user_login as autor_login,
                    ph.data_ruchu as created_at,
                    COALESCE(sur.nazwa, '') as surowiec_nazwa,
                    COALESCE(sur.nr_palety, '') as nr_palety
                FROM palety_historia ph
                LEFT JOIN magazyn_surowce sur ON ph.paleta_id = sur.id
                WHERE 1=1
                  {line_cond_ph}
                  {date_cond_ph}
                  {stacja_cond_ph}
                  {sur_cond_ph}
                ORDER BY ph.id DESC LIMIT {limit}
            """
            cursor.execute(query_ph, tuple(line_params_ph + date_params_ph + stacja_params_ph + sur_params_ph))
            rows_ph = cursor.fetchall()

            # 2. Pobierz z legacy magazyn_ruch (PSD)
            rows_psd = []
            if linia in ('ALL', 'PSD'):
                query_psd = f"""
                    SELECT 
                        r.id, 
                        r.surowiec_id as paleta_id,
                        'PSD' as linia_ruch,
                        'surowiec' as typ_palety,
                        r.typ_ruchu, 
                        r.lokalizacja as lokalizacja_zrodlowa,
                        COALESCE(r.zbiornik, r.lokalizacja) as lokalizacja_docelowa,
                        r.komentarz,
                        r.autor_login, 
                        r.created_at as created_at,
                        COALESCE(NULLIF(r.surowiec_nazwa, ''), pal.nazwa, 'Surowiec') as surowiec_nazwa,
                        COALESCE(pal.nr_palety, '') as nr_palety
                    FROM magazyn_ruch r
                    LEFT JOIN magazyn_surowce pal ON r.surowiec_id = pal.id
                    WHERE r.typ_ruchu IN ('PRODUKCJA', 'PRZESUNIECIE', 'dosypka', 'bufor_zasyp', 'cleaning', 'PRZYJECIE', 'WYDANIE_PRZESUNIECIE', 'KOREKTA', 'INWENTARYZACJA')
                      {stacja_cond_legacy}
                      {date_cond_psd}
                      {sur_cond_legacy}
                    ORDER BY r.id DESC LIMIT {limit}
                """
                cursor.execute(query_psd, tuple(stacja_params_legacy + date_params_psd + sur_params_legacy))
                rows_psd = cursor.fetchall()

            # 3. Pobierz z legacy magazyn_agro_ruch (AGRO)
            rows_agro = []
            if linia in ('ALL', 'AGRO'):
                query_agro = f"""
                    SELECT 
                        r.id, 
                        r.surowiec_id as paleta_id,
                        'AGRO' as linia_ruch,
                        'surowiec' as typ_palety,
                        r.typ_ruchu, 
                        r.lokalizacja as lokalizacja_zrodlowa,
                        COALESCE(r.zbiornik, r.lokalizacja) as lokalizacja_docelowa,
                        r.komentarz,
                        r.autor_login, 
                        r.autor_data as created_at,
                        COALESCE(NULLIF(r.surowiec_nazwa, ''), pal.nazwa, 'Surowiec') as surowiec_nazwa,
                        COALESCE(pal.nr_palety, '') as nr_palety
                    FROM magazyn_agro_ruch r
                    LEFT JOIN magazyn_surowce pal ON r.surowiec_id = pal.id
                    WHERE r.typ_ruchu IN ('PRODUKCJA', 'PRZESUNIECIE', 'dosypka', 'bufor_zasyp', 'cleaning', 'PRZYJECIE', 'WYDANIE_PRZESUNIECIE', 'KOREKTA', 'INWENTARYZACJA')
                      {stacja_cond_legacy}
                      {date_cond_agro}
                      {sur_cond_legacy}
                    ORDER BY r.id DESC LIMIT {limit}
                """
                cursor.execute(query_agro, tuple(stacja_params_legacy + date_params_agro + sur_params_legacy))
                rows_agro = cursor.fetchall()

            all_rows = rows_ph + rows_psd + rows_agro

            # Sortowanie po dacie i deduplikacja
            def parse_dt(r):
                dt = r.get('created_at')
                if isinstance(dt, datetime):
                    return dt
                if isinstance(dt, str):
                    try: return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                    except Exception: pass
                return datetime.min

            all_rows.sort(key=parse_dt, reverse=True)

            seen = set()
            deduped = []
            for r in all_rows:
                dt = parse_dt(r)
                dt_key = dt.strftime('%Y-%m-%d %H:%M') if dt != datetime.min else '-'
                key = f"{dt_key}_{r.get('paleta_id')}_{r.get('typ_ruchu')}_{r.get('lokalizacja_docelowa')}_{r.get('autor_login')}"
                if key in seen:
                    continue
                seen.add(key)

                stacja_val = r.get('lokalizacja_docelowa') or r.get('lokalizacja_zrodlowa') or '-'
                nazwa_val = r.get('surowiec_nazwa') or '-'
                if not nazwa_val or nazwa_val == '-':
                    if r.get('komentarz') and ':' in r['komentarz']:
                        nazwa_val = r['komentarz'].split(':')[1].split('->')[0].strip()
                
                # Wyciągnij ilość jeśli jest w komentarzu
                ilosc_val = 0.0
                if r.get('komentarz') and 'ilość:' in str(r.get('komentarz')):
                    try:
                        import re
                        m = re.search(r'ilość:\s*([\d\.]+)', str(r['komentarz']))
                        if m: ilosc_val = float(m.group(1))
                    except Exception: pass

                deduped.append({
                    'id': r['id'],
                    'data': dt.strftime('%Y-%m-%d %H:%M') if dt != datetime.min else '-',
                    'linia': r.get('linia_ruch') or 'PSD',
                    'stacja': stacja_val,
                    'nazwa': nazwa_val or '-',
                    'nr_palety': r.get('nr_palety') or '-',
                    'ilosc': ilosc_val,
                    'typ': r.get('typ_ruchu') or '-',
                    'user': r.get('autor_login') or '-',
                    'komentarz': r.get('komentarz') or '-'
                })

            return deduped[:limit]
        except Exception as e:
            print(f"[WarehouseHistoryService] Błąd pobierania historii: {e}")
            return []
        finally:
            conn.close()
