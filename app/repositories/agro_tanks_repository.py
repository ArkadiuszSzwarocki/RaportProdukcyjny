import logging
from app.db import get_db_connection, get_table_name
import datetime
import os
import re

_DODATEK_NAME_REGEX = re.compile(r'DODATEK')

def _normalize_tank_code(value):
    normalized = str(value or '').strip().upper()
    return normalized or None

def _classify_tank_zone(tank_code):
    normalized = _normalize_tank_code(tank_code)
    if not normalized:
        return 'BRAK'
    if normalized.startswith('BB'):
        return 'BB'
    if normalized.startswith('MZ'):
        return 'MZ'
    if normalized.startswith('KO'):
        return 'KO'
    return 'INNE'

def _is_additive_material(material_name, material_location=None):
    name = str(material_name or '').upper()
    location = str(material_location or '').upper()
    if location.startswith('DOD'):
        return True
    return bool(_DODATEK_NAME_REGEX.search(name))

def _get_auto_pallet_cooldown_seconds():
    """Return cooldown for auto pallet registration (seconds)."""
    raw_value = os.getenv('AGRO_AUTO_PALLET_COOLDOWN_SECONDS', '0')
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid AGRO_AUTO_PALLET_COOLDOWN_SECONDS=%r. Falling back to 0s.",
            raw_value,
        )
        return 0.0
    return max(0.0, parsed)

def _select_preferred_printer(cursor):
    """Pick production printer first, then fallback to any active printer."""
    cursor.execute(
        """
        SELECT id, nazwa, ip, lokalizacja
        FROM drukarki
        WHERE aktywna = 1
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                ELSE 2
            END,
            id ASC
        LIMIT 1
        """
    )
    return cursor.fetchone()

def _sanitize_zpl_text(value, max_length=64):
    text = str(value or '')
    text = text.replace('^', ' ').replace('~', ' ')
    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text

def _format_quantity_label(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return '0'

    if abs(numeric - round(numeric)) < 1e-6:
        return str(int(round(numeric)))
    return f"{numeric:.2f}".rstrip('0').rstrip('.')

class AgroTanksRepository:
    def get_production_tanks():
            return {
                'BB': list(BB_TANK_CODES),
                'MZ': list(MZ_TANK_CODES),
                'KO': list(KO_TANK_CODES),
                'CZ': list(CZ_TANK_CODES),
                'ALL': list(PRODUCTION_TANK_CODES),
            }

    def normalize_production_tank(tank_code):
            normalized = _normalize_tank_code(tank_code)
            if not normalized:
                return None
            return normalized if normalized in PRODUCTION_TANK_CODES else None

    def get_production_moves(limit=100, linia='Agro'):
            table_surowce = get_table_name('magazyn_surowce', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                # include plan name via join if available
                try:
                    table_plan = get_table_name('plan_produkcji', linia)
                    plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                    plan_select = ", p.produkt as plan_name"
                except Exception:
                    plan_join = ""
                    plan_select = ", NULL as plan_name"

                q = (
                    f"SELECT r.*, COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, s.lokalizacja as lokalizacja{plan_select} "
                    f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                    "WHERE r.typ_ruchu = 'PRODUKCJA' "
                    "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
                )
                cursor.execute(q, (limit,))
                return cursor.fetchall()
            finally:
                conn.close()

    def return_from_production(surowiec_id, ilosc, worker_login, plan_id=None, linia='Agro', komentarz=None, ruch_produkcja_id=None, lokalizacja=None):
            """Zwrot surowca z produkcji na magazyn — zwiększa stan palety.
            
            ruch_produkcja_id: opcjonalne ID ruchu PRODUKCJA, którego dotyczy zwrot.
            lokalizacja: docelowa lokalizacja (regał) — jeśli podana, aktualizuje lokalizację palety.
            """
            table_surowce = get_table_name('magazyn_surowce', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()

                cursor.execute(f"UPDATE {table_surowce} SET stan_magazynowy = stan_magazynowy + %s WHERE id = %s", (ilosc, surowiec_id))

                # Aktualizuj lokalizację palety jeśli podano
                if lokalizacja:
                    cursor.execute(f"UPDATE {table_surowce} SET lokalizacja = %s WHERE id = %s", (lokalizacja, surowiec_id))

                cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
                stan_po = cursor.fetchone()[0]

                plan_id_val = int(plan_id) if plan_id not in (None, '', 0, '0') else None
                ruch_ref = int(ruch_produkcja_id) if ruch_produkcja_id not in (None, '', 0, '0') else None
                lok_val = lokalizacja.strip() if lokalizacja and str(lokalizacja).strip() else None
                cursor.execute(
                    f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, ruch_zrodlowy_id, lokalizacja) "
                    "VALUES (%s, 'ZWROT', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s, %s, %s)",
                    (surowiec_id, ilosc, stan_po, worker_login, datetime.now(), worker_login, datetime.now(), plan_id_val, komentarz, ruch_ref, lok_val)
                )

                # Log to palety_historia
                cursor.execute(f"SELECT nazwa FROM {table_surowce} WHERE id = %s", (surowiec_id,))
                s_row = cursor.fetchone()
                s_name = s_row[0] if s_row else 'surowiec'
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'ZWROT', %s, %s, %s)",
                    (surowiec_id, linia, lok_val, f"Zwrot z produkcji ({ilosc} kg): {s_name}", worker_login)
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def get_production_items_for_return(linia='Agro', limit=200):
            """Zwraca listę ruchów PRODUKCJA z informacją ile jeszcze nie zwrócono.
            
            Każdy wiersz: ruch_id, surowiec_id, nazwa, lokalizacja, ilosc_pobrana, ilosc_zwrocona,
            ilosc_korekta, do_zwrotu, plan_id, plan_name, data, zbiornik.
            """
            table_surowce = get_table_name('magazyn_surowce', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                try:
                    table_plan = get_table_name('plan_produkcji', linia)
                    plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                    plan_select = ", p.produkt as plan_name"
                except Exception:
                    plan_join = ""
                    plan_select = ", NULL as plan_name"

                q = (
                    f"SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa, "
                    f"s.lokalizacja, ABS(r.ilosc) as ilosc_pobrana, "
                    f"COALESCE((SELECT SUM(z.ilosc) FROM {table_ruch} z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as ilosc_zwrocona, "
                    f"COALESCE((SELECT SUM(k.ilosc) FROM {table_ruch} k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as ilosc_korekta, "
                    f"r.plan_id, r.autor_login, r.autor_data, r.zbiornik{plan_select} "
                    f"FROM {table_ruch} r LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id {plan_join} "
                    "WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
                    "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
                )
                cursor.execute(q, (limit,))
                rows = cursor.fetchall()
                result = []
                for r in rows:
                    pobrana = float(r.get('ilosc_pobrana') or 0)
                    zwrocona = float(r.get('ilosc_zwrocona') or 0)
                    korekta = float(r.get('ilosc_korekta') or 0)
                    do_zwrotu = round(pobrana - zwrocona + korekta, 2)
                    if do_zwrotu <= 0:
                        continue  # w pełni zwrócone
                    result.append({
                        'ruch_id': r['ruch_id'],
                        'surowiec_id': r.get('surowiec_id'),
                        'nazwa': r.get('nazwa') or '',
                        'lokalizacja': r.get('lokalizacja') or '',
                        'ilosc_pobrana': pobrana,
                        'ilosc_zwrocona': zwrocona,
                        'ilosc_korekta': korekta,
                        'do_zwrotu': do_zwrotu,
                        'plan_id': r.get('plan_id'),
                        'plan_name': r.get('plan_name') or '',
                        'autor_login': r.get('autor_login') or '',
                        'data': r['autor_data'].strftime('%d.%m.%Y %H:%M') if r.get('autor_data') else '',
                        'zbiornik': r.get('zbiornik') or '',
                    })
                return result
            finally:
                conn.close()

    def get_production_inventory(limit=500, linia='Agro'):
            """Zwraca bieżące stany surowców pozostających w produkcji (BB/MZ/KO)."""
            table_surowce = get_table_name('magazyn_surowce', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)
            table_palety = 'magazyn_surowce'
            
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                try:
                    table_plan = get_table_name('plan_produkcji', linia)
                    plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                    plan_select = ", p.produkt as plan_name"
                except Exception:
                    plan_join = ""
                    plan_select = ", NULL as plan_name"

                q = (
                    f"SELECT r.id as ruch_id, r.surowiec_id, COALESCE(s.nazwa, r.surowiec_nazwa) as nazwa, "
                    f"s.lokalizacja, ABS(r.ilosc) as ilosc_pobrana, pal.nr_palety, "
                    f"COALESCE((SELECT SUM(z.ilosc) FROM {table_ruch} z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as ilosc_zwrocona, "
                    f"COALESCE((SELECT SUM(k.ilosc) FROM {table_ruch} k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as ilosc_korekta, "
                    f"r.plan_id, r.autor_login, r.autor_data, r.zbiornik{plan_select} "
                    f"FROM {table_ruch} r "
                    f"LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id "
                    f"LEFT JOIN {table_palety} pal ON r.surowiec_id = pal.id "
                    f"{plan_join} "
                    "WHERE r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
                    "AND COALESCE(NULLIF(TRIM(r.zbiornik), ''), '') <> '' "
                    "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
                )
                cursor.execute(q, (limit,))
                rows = cursor.fetchall()

                result = []
                for r in rows:
                    pobrana = float(r.get('ilosc_pobrana') or 0)
                    zwrocona = float(r.get('ilosc_zwrocona') or 0)
                    korekta = float(r.get('ilosc_korekta') or 0)
                    stan_systemowy = round(pobrana - zwrocona + korekta, 2)
                    if stan_systemowy <= 0:
                        continue

                    zbiornik = _normalize_tank_code(r.get('zbiornik'))
                    strefa = _classify_tank_zone(zbiornik)
                    rodzaj = 'DODATKI' if _is_additive_material(r.get('nazwa'), r.get('lokalizacja')) else 'SUROWCE'

                    result.append({
                        'ruch_id': r['ruch_id'],
                        'surowiec_id': r.get('surowiec_id'),
                        'nr_palety': r.get('nr_palety') or '',
                        'nazwa': r.get('nazwa') or '',
                        'lokalizacja': r.get('lokalizacja') or '',
                        'zbiornik': zbiornik or '',
                        'strefa': strefa,
                        'rodzaj': rodzaj,
                        'ilosc_pobrana': pobrana,
                        'ilosc_zwrocona': zwrocona,
                        'ilosc_korekta': korekta,
                        'stan_systemowy': stan_systemowy,
                        'plan_id': r.get('plan_id'),
                        'plan_name': r.get('plan_name') or '',
                        'autor_login': r.get('autor_login') or '',
                        'data': r['autor_data'].strftime('%d.%m.%Y %H:%M') if r.get('autor_data') else '',
                    })

                return result
            finally:
                conn.close()

    def get_production_inventory_snapshot(limit=4000, linia='Agro', show_empty=False):
            """Zwraca aktualny snapshot produkcji: maksymalnie 1 surowiec na zbiornik.

            Snapshot wybiera najnowszy aktywny wpis (stan_systemowy > 0) dla każdego zbiornika.
            Gdy show_empty=True, zwraca również puste zdefiniowane zbiorniki.
            """
            rows = AgroTanksRepository.get_production_inventory(limit=limit, linia=linia)
            by_tank = {}

            for row in rows:
                tank_code = _normalize_tank_code(row.get('zbiornik'))
                if not tank_code:
                    continue
                if tank_code in by_tank:
                    continue

                item = dict(row)
                item['zbiornik'] = tank_code
                item['surowiec_nazwa'] = item.get('nazwa') or ''
                item['plan_nazwa'] = item.get('plan_name') or ''
                item['is_empty'] = False
                by_tank[tank_code] = item

            if show_empty:
                for tank_code in AgroTanksRepository.get_production_tanks().get('ALL', []):
                    if tank_code in by_tank:
                        continue
                    by_tank[tank_code] = {
                        'ruch_id': None,
                        'surowiec_id': None,
                        'nr_palety': '',
                        'nazwa': '',
                        'surowiec_nazwa': '',
                        'lokalizacja': '',
                        'zbiornik': tank_code,
                        'strefa': _classify_tank_zone(tank_code),
                        'rodzaj': '',
                        'ilosc_pobrana': 0.0,
                        'ilosc_zwrocona': 0.0,
                        'ilosc_korekta': 0.0,
                        'stan_systemowy': 0.0,
                        'plan_id': None,
                        'plan_name': '',
                        'plan_nazwa': '',
                        'autor_login': '',
                        'data': '',
                        'is_empty': True,
                    }

            def _tank_sort_key(item):
                tank = item.get('zbiornik') or ''
                zone = _classify_tank_zone(tank)
                zone_rank = {'BB': 0, 'MZ': 1, 'KO': 2, 'INNE': 3, 'BRAK': 4}.get(zone, 9)
                return (zone_rank, tank)

            return sorted(by_tank.values(), key=_tank_sort_key)

    def get_production_tank_history(tank_code, limit=300, linia='Agro'):
            """Zwraca historię ruchów dla wskazanego zbiornika produkcyjnego."""
            table_surowce = get_table_name('magazyn_surowce', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)
            normalized_tank = _normalize_tank_code(tank_code)
            if not normalized_tank:
                return []

            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                try:
                    table_plan = get_table_name('plan_produkcji', linia)
                    plan_join = f" LEFT JOIN {table_plan} p ON r.plan_id = p.id "
                    plan_select = ", p.produkt as plan_name"
                except Exception:
                    plan_join = ""
                    plan_select = ", NULL as plan_name"

                q = (
                    f"SELECT r.id, r.typ_ruchu, r.ilosc, r.ilosc_po, r.status, r.autor_login, r.autor_data, r.komentarz, "
                    f"COALESCE(s.nazwa, r.surowiec_nazwa) as surowiec_nazwa, r.plan_id, r.zbiornik{plan_select} "
                    f"FROM {table_ruch} r "
                    f"LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id "
                    f"{plan_join} "
                    "WHERE UPPER(TRIM(COALESCE(r.zbiornik, ''))) = %s "
                    "AND r.typ_ruchu IN ('PRODUKCJA', 'ZWROT', 'INWENTARYZACJA_PROD') "
                    "ORDER BY r.autor_data DESC, r.id DESC LIMIT %s"
                )
                cursor.execute(q, (normalized_tank, limit))
                rows = cursor.fetchall()

                result = []
                for r in rows:
                    result.append({
                        'id': r.get('id'),
                        'typ_ruchu': r.get('typ_ruchu') or '',
                        'ilosc': float(r.get('ilosc') or 0),
                        'ilosc_po': float(r.get('ilosc_po') or 0),
                        'status': r.get('status') or '',
                        'autor_login': r.get('autor_login') or '',
                        'autor_data': r['autor_data'].strftime('%d.%m.%Y %H:%M') if r.get('autor_data') else '',
                        'komentarz': r.get('komentarz') or '',
                        'surowiec_nazwa': r.get('surowiec_nazwa') or '',
                        'plan_id': r.get('plan_id'),
                        'plan_name': r.get('plan_name') or '',
                        'zbiornik': _normalize_tank_code(r.get('zbiornik')) or normalized_tank,
                    })

                return result
            finally:
                conn.close()

    def adjust_production_inventory(ruch_id, actual_qty, worker_login, linia='Agro', komentarz=None):
            """Korekta stanu surowca będącego w produkcji (BB/MZ/KO) dla wskazanego ruchu PRODUKCJA."""
            table_ruch = get_table_name('magazyn_ruch', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    f"SELECT id, surowiec_id, COALESCE(surowiec_nazwa, '') as surowiec_nazwa, plan_id, zbiornik "
                    f"FROM {table_ruch} WHERE id = %s AND typ_ruchu = 'PRODUKCJA' AND status = 'POTWIERDZONE'",
                    (ruch_id,)
                )
                base_move = cursor.fetchone()
                if not base_move:
                    return False, 'Nie znaleziono ruchu PRODUKCJA do korekty.'

                cursor.execute(
                    f"SELECT ABS(COALESCE(ilosc, 0)) as ilosc_pobrana FROM {table_ruch} WHERE id = %s",
                    (ruch_id,)
                )
                pobrana_row = cursor.fetchone() or {}
                pobrana = float(pobrana_row.get('ilosc_pobrana') or 0)

                cursor.execute(
                    f"SELECT COALESCE(SUM(ilosc), 0) as ilosc_zwrocona FROM {table_ruch} "
                    "WHERE ruch_zrodlowy_id = %s AND typ_ruchu = 'ZWROT'",
                    (ruch_id,)
                )
                zwrot_row = cursor.fetchone() or {}
                zwrocona = float(zwrot_row.get('ilosc_zwrocona') or 0)

                cursor.execute(
                    f"SELECT COALESCE(SUM(ilosc), 0) as ilosc_korekta FROM {table_ruch} "
                    "WHERE ruch_zrodlowy_id = %s AND typ_ruchu = 'INWENTARYZACJA_PROD'",
                    (ruch_id,)
                )
                korekta_row = cursor.fetchone() or {}
                korekta = float(korekta_row.get('ilosc_korekta') or 0)

                current_qty = round(pobrana - zwrocona + korekta, 3)
                delta = round(float(actual_qty) - current_qty, 3)
                if abs(delta) < 0.001:
                    return True, None

                zbiornik_val = _normalize_tank_code(base_move.get('zbiornik'))
                opis = (komentarz or 'Inwentaryzacja produkcji').strip()
                if zbiornik_val:
                    opis = f"{opis} ({zbiornik_val})"

                cursor.execute(
                    f"INSERT INTO {table_ruch} "
                    "(surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, ruch_zrodlowy_id, zbiornik) "
                    "VALUES (%s, %s, 'INWENTARYZACJA_PROD', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        base_move.get('surowiec_id'),
                        base_move.get('surowiec_nazwa') or None,
                        delta,
                        float(actual_qty),
                        worker_login,
                        datetime.now(),
                        worker_login,
                        datetime.now(),
                        base_move.get('plan_id'),
                        opis,
                        ruch_id,
                        zbiornik_val,
                    )
                )
                conn.commit()
                return True, None
            except Exception as e:
                conn.rollback()
                return False, str(e)
            finally:
                conn.close()

    def get_current_running_plan(linia='Agro'):
            """Return current running production plan info for given line or None.

            Returns dict: {'id': <int>, 'produkt': <str>} or None.
            """
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                try:
                    table_plan = get_table_name('plan_produkcji', linia)
                except Exception:
                    table_plan = get_table_name('plan_produkcji', None)
                cursor.execute(f"SELECT id, produkt FROM {table_plan} WHERE status='w toku' ORDER BY real_start DESC LIMIT 1")
                row = cursor.fetchone()
                if not row:
                    return None
                return { 'id': int(row[0]), 'produkt': row[1] }
            finally:
                conn.close()

    def get_active_workowanie_plan(linia='Agro', target_date=None):
            """Helper to find specifically an active Workowanie plan."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                table_plan = get_table_name('plan_produkcji', linia)

                base_query = (
                    f"SELECT id, produkt, data_planu, typ_produkcji, start_machine_counter, "
                    f"start_pallet_counter, opakowanie_id "
                    f"FROM {table_plan} WHERE status IN ('w toku', 'zawieszone') AND sekcja IN ('Workowanie', 'Czyszczenie')"
                )

                if target_date:
                    query = f"{base_query} AND DATE(data_planu) = %s ORDER BY real_start DESC LIMIT 1"
                    cursor.execute(query, (target_date,))
                    return cursor.fetchone()

                # Prefer today's active plan, but allow rollover plans that started earlier
                # and are still running (e.g. long shifts crossing midnight).
                todays_query = f"{base_query} AND DATE(data_planu) = CURDATE() ORDER BY real_start DESC LIMIT 1"
                cursor.execute(todays_query)
                plan = cursor.fetchone()
                if plan:
                    return plan

                fallback_query = f"{base_query} ORDER BY real_start DESC LIMIT 1"
                cursor.execute(fallback_query)
                return cursor.fetchone()
            finally:
                conn.close()

    def get_finished_plans_of_day(linia='Agro', target_date=None):
            """Helper to find finished Workowanie plans for a specific day."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                table_plan = get_table_name('plan_produkcji', linia)
                
                query = f"SELECT id, produkt, data_planu, typ_produkcji, opakowanie_id FROM {table_plan} WHERE status='zakonczone' AND sekcja IN ('Workowanie', 'Czyszczenie')"
                params = []
                
                if target_date:
                    query += " AND DATE(data_planu) = %s"
                    params.append(target_date)
                else:
                    query += " AND DATE(data_planu) = CURDATE()"
                    
                query += " ORDER BY real_stop DESC"
                cursor.execute(query, params)
                return cursor.fetchall()
            finally:
                conn.close()

    def auto_register_pallet(plan_id, linia='AGRO', source_instance=None):
            """Automatically registers a 1000kg pallet for a given plan."""
            from app.utils.pallet_id import generate_pallet_id
            # removed PlanningService
            from app.core.audit import audit_log
            
            table_plan = get_table_name('plan_produkcji', linia)
            table_pal = get_table_name('palety_workowanie', linia)
            
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                
                # Acquire database-level lock to prevent concurrency race conditions on MyISAM storage engine
                cursor.execute("SELECT GET_LOCK('agro_pallet_register', 10)")
                lock_res = cursor.fetchone()
                if not lock_res or lock_res[0] != 1:
                    return False
                
                # Reset transaction snapshot so we see the latest committed data in repeatable-read isolation
                conn.commit()
                
                # Fetch plan info
                cursor.execute(f"SELECT produkt, sekcja FROM {table_plan} WHERE id=%s", (plan_id,))
                plan_row = cursor.fetchone()
                if not plan_row:
                    return False
                
                plan_produkt, plan_sekcja = plan_row
                if plan_sekcja not in ('Workowanie', 'Czyszczenie'):
                    return False
                
                waga_input = 1000
                now_ts = datetime.now()
                user_login = 'System'
                source_instance = str(source_instance or 'unknown')[:120]
                cooldown_seconds = _get_auto_pallet_cooldown_seconds()
                
                # Optional cooldown can be used as an emergency guard against hardware bit flickering.
                if cooldown_seconds > 0:
                    cursor.execute(
                        f"SELECT MAX(data_dodania) FROM {table_pal} WHERE plan_id = %s",
                        (plan_id,)
                    )
                    latest_row = cursor.fetchone()
                    if latest_row and latest_row[0]:
                        latest_date = latest_row[0]
                        if isinstance(latest_date, str):
                            try:
                                latest_date = datetime.strptime(latest_date, '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                pass

                        time_diff = (now_ts - latest_date).total_seconds()
                        if time_diff < cooldown_seconds:
                            logger.warning(
                                "[COOLDOWN] Skipped auto-registering pallet for plan_id=%s. "
                                "Last pallet added %.1fs ago (cooldown %.1fs).",
                                plan_id,
                                time_diff,
                                cooldown_seconds,
                            )
                            return False
                
                nr_palety = None
                paleta_id = None

                # Consume the oldest reserved label first, if available.
                cursor.execute(
                    f"SELECT id, nr_palety FROM {table_pal} WHERE plan_id = %s AND COALESCE(status, '') = 'rezerwacja' ORDER BY id ASC LIMIT 1",
                    (plan_id,),
                )
                reserved_row = cursor.fetchone()

                if reserved_row:
                    paleta_id = reserved_row[0]
                    nr_palety = reserved_row[1] or generate_pallet_id(linia)
                    cursor.execute(
                        f"UPDATE {table_pal} SET waga = %s, tara = 25, waga_brutto = 0, data_dodania = %s, status = 'do_przyjecia', dodal_login = %s, nr_palety = %s WHERE id = %s",
                        (waga_input, now_ts, user_login, nr_palety, paleta_id),
                    )
                else:
                    nr_palety = generate_pallet_id(linia)
                    cursor.execute(
                        f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s)",
                        (plan_id, waga_input, now_ts, user_login, nr_palety),
                    )
                    paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
                
                # Update plan tonnage
                cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
                    (waga_input, plan_id),
                )
                
                # Compute sequential pallet number (nr_palety_lp) for this plan and store it if column exists
                try:
                    if paleta_id:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
                        res_lp = cursor.fetchone()
                        nr_palety_lp = int(res_lp[0]) if res_lp else 1
                        try:
                            cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                            if cursor.fetchone():
                                cursor.execute(f"UPDATE {table_pal} SET nr_palety_lp = %s WHERE id = %s", (nr_palety_lp, paleta_id))
                        except Exception:
                            pass
                except Exception:
                    pass
                
                conn.commit()
                
                # Ensure status is updated (e.g. from 'w toku' to 'zakonczone' if target reached, though usually stays 'w toku')
                from app.services.planning.status import PlanningStatusService
                try:
                    PlanningStatusService.ensure_status_after_tonaz_update(plan_id, linia=linia)
                except Exception:
                    pass

                if paleta_id:
                    try:
                        from app.utils.pallet_label import prepare_pallet_label_data
                        from app.services.print_server import get_printer

                        label_data = prepare_pallet_label_data(cursor, paleta_id, linia, source_table='workowanie')
                        if not label_data:
                            logger.warning(
                                'System auto-print skipped: missing label data for paleta_id=%s (plan_id=%s, source=%s)',
                                paleta_id,
                                plan_id,
                                source_instance,
                            )
                        else:
                            printer = get_printer()
                            printer_row = _select_preferred_printer(cursor)
                            override_name = None
                            override_ip = None
                            if printer_row:
                                override_name = printer_row[1] if len(printer_row) > 1 else None
                                override_ip = printer_row[2] if len(printer_row) > 2 else None

                            for copy_num in range(1, 3):
                                ok, print_msg = printer.print_finished_product_label(
                                    label_data,
                                    override_ip=override_ip,
                                    override_name=override_name,
                                )
                                logger.info(
                                    'System auto-print copy %s/2 for paleta=%s (plan_id=%s, source=%s): success=%s, printer=%s, ip=%s, msg=%s',
                                    copy_num,
                                    nr_palety,
                                    plan_id,
                                    source_instance,
                                    ok,
                                    override_name or printer.printer_name,
                                    override_ip or printer.printer_ip,
                                    print_msg,
                                )
                                if not ok:
                                    break
                    except Exception as print_err:
                        logger.error(
                            'System auto-print failed for paleta=%s (plan_id=%s, source=%s): %s',
                            nr_palety,
                            plan_id,
                            source_instance,
                            print_err,
                        )
                    
                audit_log(
                    'System: Automatycznie dodano paletę',
                    f'plan_id={plan_id}, produkt={plan_produkt}, waga={waga_input} kg, source_instance={source_instance}',
                )
                return True
            finally:
                try:
                    cursor.execute("SELECT RELEASE_LOCK('agro_pallet_register')")
                except Exception:
                    pass
                conn.close()

    def rename_pallet(surowiec_id, new_name, worker_login, linia='Agro'):
            table_surowce = get_table_name('magazyn_surowce', linia)
            table_ruch = get_table_name('magazyn_ruch', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                # get current qty
                cursor.execute(f"SELECT stan_magazynowy FROM {table_surowce} WHERE id = %s", (surowiec_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                stan = row[0]

                # update name
                cursor.execute(f"UPDATE {table_surowce} SET nazwa = %s WHERE id = %s", (new_name, surowiec_id))

                # insert history record for audit
                cursor.execute(
                    f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, komentarz) "
                    "VALUES (%s, 'KOREKTA', %s, %s, 'POTWIERDZONE', %s, %s, %s, %s, %s)",
                    (surowiec_id, 0, stan, worker_login, datetime.now(), worker_login, datetime.now(), f'Zmiana nazwy na: {new_name}')
                )
                conn.commit()
                return True
            finally:
                conn.close()

