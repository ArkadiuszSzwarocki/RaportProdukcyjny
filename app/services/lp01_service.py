from datetime import datetime
from app.core.database import get_db_connection
from app.db import get_table_name
import re

class Lp01Service:
    @staticmethod
    def _categorize_item(nazwa, typ_opakowania=''):
        n = str(nazwa or '').lower()
        t = str(typ_opakowania or '').lower()
        if 'etykiet' in n:
            return 'Etykieta', 'badge-warning', 'label'
        if 'kalka' in n:
            return 'Kalka', 'badge-info', 'print'
        if 'włóknina' in n or 'wloknina' in n or 'sms' in n:
            return 'Włóknina SMS', 'badge-success', 'layers'
        if 'folia' in n or 'kaptur' in n or 'stretch' in n or 'rolka' in t:
            return 'Folia', 'badge-primary', 'album'
        return 'Inny materiał', 'badge-secondary', 'inventory_2'

    @staticmethod
    def get_active_lp01_items(linia='AGRO'):
        """
        Zwraca wszystkie materiały aktualnie znajdujące się na maszynie LP01
        wraz z czasem dostarczenia, operatorem i lokalizacją źródłową.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_opk = get_table_name('magazyn_opakowania', linia)
            
            # Pobierz aktywne pozycje z magazyn_opakowania na LP01 (oraz Maszyna)
            cursor.execute(f"""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, 
                       typ_opakowania, created_at, updated_at, linia, is_blocked
                FROM {table_opk}
                WHERE UPPER(lokalizacja) IN ('LP01', 'MASZYNA')
                  AND stan_magazynowy > 0
                ORDER BY updated_at DESC, id DESC
            """)
            opk_items = cursor.fetchall() or []

            # Sprawdź też magazyn_surowce (na wypadek gdyby tam zarejestrowano np. folię lub surowiec)
            table_sur = get_table_name('magazyn_surowce', linia)
            cursor.execute(f"""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii,
                       'Surowiec' as typ_opakowania, created_at, updated_at, linia, is_blocked
                FROM {table_sur}
                WHERE UPPER(lokalizacja) IN ('LP01', 'MASZYNA')
                  AND stan_magazynowy > 0
                ORDER BY updated_at DESC, id DESC
            """)
            sur_items = cursor.fetchall() or []

            all_items = []
            for row in (opk_items + sur_items):
                p_id = row['id']
                sscc = row.get('nr_palety') or ''
                
                # Ustal czas i szczegóły dostarczenia na LP01 z palety_historia
                cursor.execute("""
                    SELECT data_ruchu, user_login, lokalizacja_zrodlowa, akcja, komentarz
                    FROM palety_historia
                    WHERE (paleta_id = %s OR (nr_palety IS NOT NULL AND nr_palety = %s))
                      AND UPPER(COALESCE(lokalizacja_docelowa, '')) IN ('LP01', 'MASZYNA')
                    ORDER BY data_ruchu DESC, id DESC
                    LIMIT 1
                """, (p_id, sscc))
                hist_row = cursor.fetchone()

                dostarczono_at = None
                dostarczyl_user = 'Nieznany'
                zrodlo_loc = 'Magazyn'

                if hist_row:
                    dostarczono_at = hist_row.get('data_ruchu')
                    dostarczyl_user = hist_row.get('user_login') or 'Nieznany'
                    zrodlo_loc = hist_row.get('lokalizacja_zrodlowa') or 'Magazyn'
                else:
                    # Fallback do magazyn_ruch
                    cursor.execute("""
                        SELECT autor_data, autor_login, komentarz
                        FROM magazyn_ruch
                        WHERE (surowiec_id = %s OR surowiec_nazwa = %s)
                          AND UPPER(COALESCE(lokalizacja, '')) IN ('LP01', 'MASZYNA')
                        ORDER BY id DESC
                        LIMIT 1
                    """, (p_id, row.get('nazwa')))
                    ruch_row = cursor.fetchone()
                    if ruch_row:
                        dostarczono_at = ruch_row.get('autor_data')
                        dostarczyl_user = ruch_row.get('autor_login') or 'Nieznany'
                        m = re.search(r'Z\s+([A-Za-z0-9_-]+)\s+do', ruch_row.get('komentarz') or '')
                        if m:
                            zrodlo_loc = m.group(1)
                    else:
                        dostarczono_at = row.get('updated_at') or row.get('created_at')

                kategoria, badge_cls, icon_name = Lp01Service._categorize_item(row.get('nazwa'), row.get('typ_opakowania'))

                all_items.append({
                    'id': p_id,
                    'nr_palety': sscc,
                    'nazwa': row.get('nazwa') or 'Brak nazwy',
                    'stan_magazynowy': float(row.get('stan_magazynowy') or 0),
                    'lokalizacja': row.get('lokalizacja') or 'LP01',
                    'nr_partii': row.get('nr_partii') or '—',
                    'typ': 'Surowiec' if 'Surowiec' in str(row.get('typ_opakowania')) else 'Opakowanie',
                    'kategoria': kategoria,
                    'badge_class': badge_cls,
                    'icon': icon_name,
                    'dostarczono_at': dostarczono_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(dostarczono_at, datetime) else str(dostarczono_at or '—'),
                    'dostarczyl_user': dostarczyl_user,
                    'lokalizacja_zrodlowa': zrodlo_loc,
                    'is_blocked': bool(row.get('is_blocked'))
                })

            return all_items
        finally:
            conn.close()

    @staticmethod
    def get_lp01_kpis(linia='AGRO'):
        """Zwraca statystyki materiałów na maszynie LP01."""
        items = Lp01Service.get_active_lp01_items(linia=linia)
        
        labels_cnt = sum(1 for it in items if it['kategoria'] == 'Etykieta')
        kalka_cnt = sum(1 for it in items if it['kategoria'] == 'Kalka')
        sms_cnt = sum(1 for it in items if it['kategoria'] == 'Włóknina SMS')
        folia_cnt = sum(1 for it in items if it['kategoria'] == 'Folia')
        other_cnt = sum(1 for it in items if it['kategoria'] == 'Inny materiał')

        last_delivery = items[0] if items else None

        # Ostatnia archiwizacja
        conn = get_db_connection()
        last_arch = None
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT nazwa, waga_ostatnia, data_archiwizacji, user_login, komentarz
                FROM magazyn_archiwum
                WHERE UPPER(lokalizacja_ostatnia) IN ('LP01', 'MASZYNA')
                ORDER BY data_archiwizacji DESC, id DESC
                LIMIT 1
            """)
            last_arch = cur.fetchone()
        finally:
            conn.close()

        return {
            'total_active': len(items),
            'labels_count': labels_cnt,
            'kalka_count': kalka_cnt,
            'sms_count': sms_cnt,
            'folia_count': folia_cnt,
            'other_count': other_cnt,
            'last_delivery': last_delivery,
            'last_archived': last_arch
        }

    @staticmethod
    def archive_lp01_item(item_id, item_type='Opakowanie', user_login='nieznany', consumed_qty=None, linia='AGRO', komentarz=None):
        """
        Archiwizuje materiał z maszyny LP01 (oznacza jako zużyty, tworzy wpis w magazyn_archiwum,
        wyzerowuje stan na maszynie lub zmniejsza go o consumed_qty, loguje w palety_historia i magazyn_ruch).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table = get_table_name('magazyn_surowce' if item_type == 'Surowiec' else 'magazyn_opakowania', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)

            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (item_id,))
            item = cursor.fetchone()
            if not item:
                return False, "Nie znaleziono materiału na maszynie LP01."

            curr_qty = float(item.get('stan_magazynowy') or 0)
            if curr_qty <= 0:
                return False, "Materiał posiada już stan 0."

            qty_to_archive = float(consumed_qty) if consumed_qty is not None else curr_qty
            if qty_to_archive <= 0 or qty_to_archive > curr_qty:
                return False, f"Nieprawidłowa ilość do archiwizacji (dostępne na LP01: {curr_qty})."

            now = datetime.now()
            mat_name = item.get('nazwa') or item.get('produkt') or 'Materiał'
            sscc = item.get('nr_palety')
            is_partial = (qty_to_archive < curr_qty)
            comm_text = komentarz or (f"Zużycie częściowe na maszynie LP01 ({qty_to_archive} szt/kg)" if is_partial else f"Pełne zużycie materiału na maszynie LP01 ({qty_to_archive} szt/kg)")

            # 1. Zapis do magazyn_archiwum
            cursor.execute("""
                INSERT INTO magazyn_archiwum
                (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, data_archiwizacji, user_login, komentarz)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'LP01', %s, %s, %s)
            """, (
                item['id'],
                sscc,
                mat_name,
                item_type,
                item.get('linia', linia),
                item.get('nr_partii'),
                qty_to_archive,
                now,
                user_login,
                comm_text
            ))

            # 2. Aktualizacja w magazyn_opakowania
            if is_partial:
                remaining_qty = curr_qty - qty_to_archive
                cursor.execute(
                    f"UPDATE {table} SET stan_magazynowy = %s, updated_at = %s WHERE id = %s",
                    (remaining_qty, now, item_id)
                )
            else:
                cursor.execute(
                    f"UPDATE {table} SET stan_magazynowy = 0, lokalizacja = 'ZUŻYTE', updated_at = %s WHERE id = %s",
                    (now, item_id)
                )

            # 3. Zapis do palety_historia
            cursor.execute("""
                INSERT INTO palety_historia
                (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu)
                VALUES (%s, %s, %s, %s, 'ARCHIWIZACJA_LP01', 'LP01', 'ZUŻYTE', %s, %s, %s)
            """, (
                item_id,
                sscc,
                linia,
                item_type.lower(),
                comm_text,
                user_login,
                now
            ))

            # 4. Zapis do magazyn_ruch
            try:
                cursor.execute(f"""
                    INSERT INTO {table_ruch}
                    (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, lokalizacja, status, autor_login, autor_data, komentarz)
                    VALUES (%s, %s, 'ARCHIWIZACJA_LP01', %s, %s, 'ZUŻYTE', 'POTWIERDZONE', %s, %s, %s)
                """, (
                    item_id,
                    mat_name,
                    qty_to_archive,
                    (curr_qty - qty_to_archive),
                    user_login,
                    now,
                    comm_text
                ))
            except Exception as e_ruch:
                print("Lp01Service: Błąd zapisu magazyn_ruch:", e_ruch)

            conn.commit()
            return True, f"Pomyślnie zarchiwizowano zużycie materiału {mat_name} ({qty_to_archive} szt/kg)."
        except Exception as e:
            if conn: conn.rollback()
            return False, f"Błąd archiwizacji: {str(e)}"
        finally:
            conn.close()

    @staticmethod
    def get_lp01_history(linia='AGRO', limit=100):
        """Zwraca pełną historię wydań, zużyć i archiwizacji dla stanowiska LP01."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Pobierz zarchiwizowane zdarzenia z magazyn_archiwum
            cursor.execute(f"""
                SELECT id, original_id as item_id, nr_palety, nazwa, typ_palety, 
                       waga_ostatnia as ilosc, data_archiwizacji as data_zdarzenia, 
                       user_login, komentarz, 'ARCHIWIZACJA' as typ_zdarzenia
                FROM magazyn_archiwum
                WHERE UPPER(COALESCE(lokalizacja_ostatnia, '')) IN ('LP01', 'MASZYNA')
                ORDER BY data_archiwizacji DESC
                LIMIT %s
            """, (limit,))
            arch_rows = cursor.fetchall() or []

            # Pobierz zdarzenia wydań i przesunięć z palety_historia
            cursor.execute(f"""
                SELECT id, paleta_id as item_id, nr_palety, typ_palety,
                       lokalizacja_zrodlowa, lokalizacja_docelowa,
                       data_ruchu as data_zdarzenia, user_login, komentarz, akcja as typ_zdarzenia
                FROM palety_historia
                WHERE UPPER(COALESCE(lokalizacja_docelowa, '')) IN ('LP01', 'MASZYNA')
                   OR UPPER(COALESCE(lokalizacja_zrodlowa, '')) IN ('LP01', 'MASZYNA')
                ORDER BY data_ruchu DESC
                LIMIT %s
            """, (limit,))
            hist_rows = cursor.fetchall() or []

            # Połącz i uporządkuj
            events = []
            for a in arch_rows:
                kategoria, badge_cls, icon_name = Lp01Service._categorize_item(a['nazwa'])
                events.append({
                    'id': a['id'],
                    'item_id': a['item_id'],
                    'nr_palety': a.get('nr_palety') or '—',
                    'nazwa': a['nazwa'],
                    'kategoria': kategoria,
                    'badge_class': badge_cls,
                    'icon': icon_name,
                    'ilosc': float(a.get('ilosc') or 0),
                    'typ_zdarzenia': 'ZUŻYTE / ZARCHIWIZOWANE',
                    'status_badge': 'badge-danger',
                    'data': a['data_zdarzenia'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(a['data_zdarzenia'], datetime) else str(a['data_zdarzenia']),
                    'user': a.get('user_login') or 'Nieznany',
                    'komentarz': a.get('komentarz') or 'Archiwizacja ze stanowiska LP01'
                })

            for h in hist_rows:
                is_arrival = str(h.get('lokalizacja_docelowa') or '').upper() in ('LP01', 'MASZYNA')
                action_text = 'DOSTARCZENIE NA LP01' if is_arrival else 'ZWROT DO MAGAZYNU'
                badge_style = 'badge-success' if is_arrival else 'badge-warning'
                events.append({
                    'id': h['id'],
                    'item_id': h['item_id'],
                    'nr_palety': h.get('nr_palety') or '—',
                    'nazwa': h.get('komentarz') or 'Materiał',
                    'kategoria': 'Ruch',
                    'badge_class': 'badge-info',
                    'icon': 'local_shipping' if is_arrival else 'keyboard_return',
                    'ilosc': 0,
                    'typ_zdarzenia': action_text,
                    'status_badge': badge_style,
                    'data': h['data_zdarzenia'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(h['data_zdarzenia'], datetime) else str(h['data_zdarzenia']),
                    'user': h.get('user_login') or 'Nieznany',
                    'komentarz': h.get('komentarz') or f"{h.get('lokalizacja_zrodlowa')} -> {h.get('lokalizacja_docelowa')}"
                })

            def _sort_dt(x):
                try:
                    return datetime.strptime(x['data'], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    return datetime.min

            events.sort(key=_sort_dt, reverse=True)
            return events[:limit]
        finally:
            conn.close()

    @staticmethod
    def get_available_warehouse_consumables(linia='AGRO'):
        """Zwraca materiały opakowaniowe i eksploatacyjne dostępne w magazynie na regałach do wydania na LP01."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_opk = get_table_name('magazyn_opakowania', linia)
            cursor.execute(f"""
                SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, typ_opakowania
                FROM {table_opk}
                WHERE UPPER(COALESCE(lokalizacja, '')) NOT IN ('LP01', 'MASZYNA', 'ZUŻYTE', 'ARCHIWUM')
                  AND stan_magazynowy > 0
                ORDER BY nazwa ASC, lokalizacja ASC
            """)
            items = cursor.fetchall() or []
            for it in items:
                kat, b_cls, icn = Lp01Service._categorize_item(it['nazwa'], it.get('typ_opakowania'))
                it['kategoria'] = kat
                it['badge_class'] = b_cls
                it['icon'] = icn
            return items
        finally:
            conn.close()
