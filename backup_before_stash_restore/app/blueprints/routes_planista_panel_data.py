from datetime import date as _date
from datetime import datetime as _dt
from datetime import time as _time
from datetime import timedelta as _timedelta

from app.db import get_table_name


def load_primary_plan_rows(cursor, wybrana_data, wybrana_linia):
    """Load and merge primary Zasyp/Czyszczenie/Workowanie rows for planista panel."""
    table_plan = get_table_name('plan_produkcji', wybrana_linia)

    cursor.execute(
        f"""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci,
               COALESCE(uszkodzone_worki, 0) AS uszkodzone_worki,
               COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,
               zasyp_id
        FROM {table_plan}
        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
        ORDER BY kolejnosc
        """,
        (wybrana_data,),
    )
    plany_list = [dict(plan) for plan in cursor.fetchall()]

    cursor.execute(
        f"""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci,
               COALESCE(uszkodzone_worki, 0) AS uszkodzone_worki,
               COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,
               zasyp_id
        FROM {table_plan}
        WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'
        ORDER BY kolejnosc
        """,
        (wybrana_data,),
    )
    work_rows = cursor.fetchall()
    for work_row in work_rows:
        if any(plan['id'] == work_row['id'] for plan in plany_list):
            continue

        product_name = (work_row['produkt'] or '').strip().lower()
        matching_zasyp = next(
            (
                plan
                for plan in plany_list
                if plan['sekcja'].lower() == 'zasyp' and (plan['produkt'] or '').strip().lower() == product_name
            ),
            None,
        )
        if matching_zasyp is not None:
            matching_zasyp['uszkodzone_worki'] = (matching_zasyp.get('uszkodzone_worki') or 0) + (work_row.get('uszkodzone_worki') or 0)
            if matching_zasyp.get('status') == 'zakonczone':
                matching_zasyp['linked_workowanie_id'] = work_row['id']
                matching_zasyp['linked_workowanie_tonaz'] = work_row['tonaz'] or 0
                matching_zasyp['_work_nazwa'] = work_row.get('nazwa_zlecenia', '') or ''
            continue

        plany_list.append(dict(work_row))

    return plany_list


def enrich_primary_plan_carryover(cursor, plany_list, wybrana_data, wybrana_linia):
    """Add carry-over source date and original moved tonnage metadata for primary plan rows."""
    if plany_list:
        plan_ids = [plan['id'] for plan in plany_list]
        fmt_ids = ','.join(['%s'] * len(plan_ids))
        cursor.execute(
            f"""
            SELECT ph.plan_id,
                   SUBSTRING_INDEX(SUBSTRING_INDEX(ph.changes, ' na ', 1), 'Z ', -1) AS stara_data
            FROM plan_history ph
            INNER JOIN (
                SELECT plan_id, MAX(id) AS max_id FROM plan_history
                WHERE action = 'przeniesienie' AND plan_id IN ({fmt_ids})
                GROUP BY plan_id
            ) last ON last.plan_id = ph.plan_id AND last.max_id = ph.id
            """,
            plan_ids,
        )
        przeniesione_map = {row['plan_id']: row['stara_data'] for row in cursor.fetchall()}
        for plan in plany_list:
            stara = przeniesione_map.get(plan['id'])
            if stara and stara != wybrana_data:
                try:
                    plan['przeniesiony_z'] = _dt.strptime(stara, '%Y-%m-%d').strftime('%d.%m.%Y')
                except Exception:
                    plan['przeniesiony_z'] = stara
            else:
                nazwa = plan.get('nazwa_zlecenia', '') or ''
                src = ''
                for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                    if nazwa.startswith(prefix):
                        raw_date = nazwa[len(prefix):].strip()
                        try:
                            src = _dt.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                        except Exception:
                            pass
                        break
                if not src and plan.get('_work_nazwa'):
                    work_nazwa = plan['_work_nazwa']
                    for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                        if work_nazwa.startswith(prefix):
                            raw_date = work_nazwa[len(prefix):].strip()
                            try:
                                src = _dt.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                            except Exception:
                                pass
                            break
                plan['przeniesiony_z'] = src or None
            plan['przeniesiony_tonaz'] = 0

        table_bufor_local = get_table_name('bufor', wybrana_linia)
        zasyp_id_to_plan = {}
        for plan in plany_list:
            if plan.get('przeniesiony_z') and plan.get('zasyp_id'):
                zasyp_id_to_plan[plan['zasyp_id']] = plan
        if zasyp_id_to_plan:
            fmt_zids = ','.join(['%s'] * len(zasyp_id_to_plan))
            cursor.execute(
                f"""
                SELECT zasyp_id, tonaz_rzeczywisty
                FROM {table_bufor_local}
                WHERE zasyp_id IN ({fmt_zids}) AND status IN ('aktywny', 'zamkniete', 'przeniesiony')
                ORDER BY id DESC
                """,
                list(zasyp_id_to_plan.keys()),
            )
            seen = set()
            for row in cursor.fetchall():
                zasyp_id = row['zasyp_id']
                if zasyp_id not in seen:
                    seen.add(zasyp_id)
                    plan_ref = zasyp_id_to_plan[zasyp_id]
                    plan_ref['przeniesiony_tonaz'] = int(row['tonaz_rzeczywisty']) if row['tonaz_rzeczywisty'] else 0
    else:
        for plan in plany_list:
            plan['przeniesiony_z'] = None
            plan['przeniesiony_tonaz'] = 0

    return plany_list


def build_primary_plan_metrics(cursor, plany_list, wybrana_data, wybrana_linia, calculate_kg_per_hour):
    """Compute execution totals, estimated minutes and palety map for primary PSD plan rows."""
    suma_plan, suma_wyk, suma_minut_plan = 0, 0, 0
    palety_mapa = {}

    t_sz_curr = get_table_name('szarze', wybrana_linia)
    t_ds_curr = get_table_name('dosypki', wybrana_linia)
    t_pa_curr = get_table_name('palety_workowanie', wybrana_linia)
    t_pp_curr = get_table_name('plan_produkcji', wybrana_linia)

    for plan in plany_list:
        tonaz = plan['tonaz'] or 0
        typ_produkcji = plan['typ_produkcji']
        norma = calculate_kg_per_hour(typ_produkcji) if typ_produkcji else calculate_kg_per_hour('bigbag')
        dur = int((tonaz / norma) * 60) if norma > 0 else 0
        plan['estymacja_minut'] = dur

        if plan['sekcja'].lower() != 'czyszczenie':
            suma_plan += tonaz
            cursor.execute(
                f"SELECT (COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_curr} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0)) as total FROM {t_sz_curr} WHERE plan_id = %s",
                (plan['id'], plan['id']),
            )
            sz_r = cursor.fetchone()
            wyk_val = sz_r['total'] if sz_r and sz_r['total'] is not None else plan['tonaz_rzeczywisty'] or 0
            plan['tonaz_rzeczywisty'] = wyk_val
            suma_wyk += wyk_val
        suma_minut_plan += dur

        cursor.execute(
            f"SELECT pw.id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania FROM {t_pa_curr} pw JOIN {t_pp_curr} pp ON pw.plan_id = pp.id WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie' ORDER BY pw.id DESC",
            (wybrana_data, plan['produkt']),
        )
        palety_rows = cursor.fetchall()
        palety_mapa[plan['id']] = [
            (
                row['waga'],
                (row['data_dodania'].strftime('%H:%M') if hasattr(row['data_dodania'], 'strftime') else str(row['data_dodania'])),
                row['tara'],
                row['waga_brutto'],
            )
            for row in palety_rows
        ]

    return {
        'plany_list': plany_list,
        'palety_mapa': palety_mapa,
        'suma_plan': suma_plan,
        'suma_wyk': suma_wyk,
        'suma_minut_plan': suma_minut_plan,
    }


def load_agro_plan_rows(cursor, wybrana_data):
    """Load and merge AGRO plan rows for the planista panel side tab."""
    t_pp_agro = get_table_name('plan_produkcji', 'AGRO')
    cursor.execute(
        f"""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci,
               COALESCE(uszkodzone_worki, 0) AS uszkodzone_worki,
               COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,
               zasyp_id
        FROM {t_pp_agro}
        WHERE data_planu = %s
        ORDER BY kolejnosc
        """,
        (wybrana_data,),
    )
    agro_all = [dict(row) for row in cursor.fetchall()]

    zasyp_products = {(row['produkt'] or '').strip().lower() for row in agro_all if row['sekcja'].lower() == 'zasyp'}
    plany_agro = []
    zasyp_lookup = {}

    for row in agro_all:
        sekcja = row['sekcja'].lower()
        product_name = (row['produkt'] or '').strip().lower()

        if sekcja == 'zasyp':
            zasyp_lookup[product_name] = row
            plany_agro.append(row)
        elif sekcja == 'workowanie':
            if product_name in zasyp_products:
                continue
            plany_agro.append(row)
        else:
            plany_agro.append(row)

    for row in agro_all:
        if row['sekcja'].lower() == 'workowanie' and (row['produkt'] or '').strip().lower() in zasyp_products:
            product_name = (row['produkt'] or '').strip().lower()
            target = zasyp_lookup.get(product_name)
            if target:
                target['uszkodzone_worki'] = (target.get('uszkodzone_worki') or 0) + (row.get('uszkodzone_worki') or 0)

    return plany_agro


def enrich_agro_plan_carryover(cursor, plany_agro, wybrana_data):
    """Add carry-over source date and original moved tonnage metadata for AGRO panel rows."""
    if plany_agro:
        agro_ids = [plan['id'] for plan in plany_agro]
        fmt_a_ids = ','.join(['%s'] * len(agro_ids))
        cursor.execute(
            f"""
            SELECT ph.plan_id,
                   SUBSTRING_INDEX(SUBSTRING_INDEX(ph.changes, ' na ', 1), 'Z ', -1) AS stara_data
            FROM plan_history ph
            INNER JOIN (
                SELECT plan_id, MAX(id) AS max_id FROM plan_history
                WHERE action = 'przeniesienie' AND plan_id IN ({fmt_a_ids})
                GROUP BY plan_id
            ) last ON last.plan_id = ph.plan_id AND last.max_id = ph.id
            """,
            agro_ids,
        )
        przeniesione_map = {row['plan_id']: row['stara_data'] for row in cursor.fetchall()}

        for plan in plany_agro:
            stara = przeniesione_map.get(plan['id'])
            if stara and stara != wybrana_data:
                try:
                    plan['przeniesiony_z'] = _dt.strptime(stara, '%Y-%m-%d').strftime('%d.%m.%Y')
                except Exception:
                    plan['przeniesiony_z'] = stara
            else:
                nazwa = plan.get('nazwa_zlecenia', '') or ''
                src = ''
                for prefix in ('PRZENIESIONE z ', 'carry-over z '):
                    if nazwa.startswith(prefix):
                        raw_date = nazwa[len(prefix):].strip()
                        try:
                            src = _dt.strptime(raw_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                        except Exception:
                            pass
                        break
                plan['przeniesiony_z'] = src or None
            plan['przeniesiony_tonaz'] = 0

        t_bf_agro = get_table_name('bufor', 'AGRO')
        zasyp_id_to_agro = {plan['zasyp_id']: plan for plan in plany_agro if plan.get('przeniesiony_z') and plan.get('zasyp_id')}
        if zasyp_id_to_agro:
            fmt_zids_a = ','.join(['%s'] * len(zasyp_id_to_agro))
            cursor.execute(
                f"""
                SELECT zasyp_id, tonaz_rzeczywisty
                FROM {t_bf_agro}
                WHERE zasyp_id IN ({fmt_zids_a}) AND status IN ('aktywny', 'zamkniete', 'przeniesiony')
                ORDER BY id DESC
                """,
                list(zasyp_id_to_agro.keys()),
            )
            seen = set()
            for row in cursor.fetchall():
                zasyp_id = row['zasyp_id']
                if zasyp_id not in seen:
                    seen.add(zasyp_id)
                    plan_ref = zasyp_id_to_agro[zasyp_id]
                    plan_ref['przeniesiony_tonaz'] = int(row['tonaz_rzeczywisty']) if row['tonaz_rzeczywisty'] else 0
    else:
        for plan in plany_agro:
            plan['przeniesiony_z'] = None
            plan['przeniesiony_tonaz'] = 0

    return plany_agro


def build_agro_plan_metrics(cursor, plany_agro, wybrana_data, calculate_kg_per_hour, palety_mapa):
    """Compute execution totals and palety details for AGRO panel rows."""
    suma_plan_agro, suma_wyk_agro, suma_minut_plan_agro = 0, 0, 0
    t_pp_agro = get_table_name('plan_produkcji', 'AGRO')
    t_sz_agro = get_table_name('szarze', 'AGRO')
    t_ds_agro = get_table_name('dosypki', 'AGRO')
    t_pa_agro = get_table_name('palety_workowanie', 'AGRO')

    for plan in plany_agro:
        tonaz = plan['tonaz'] or 0
        typ_produkcji = plan['typ_produkcji']
        norma = calculate_kg_per_hour(typ_produkcji) if typ_produkcji else calculate_kg_per_hour('bigbag')
        dur = int((tonaz / norma) * 60) if norma > 0 else 0
        plan['estymacja_minut'] = dur

        if plan['sekcja'].lower() != 'czyszczenie':
            suma_plan_agro += tonaz
            cursor.execute(
                f"SELECT (COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_agro} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0)) as total FROM {t_sz_agro} WHERE plan_id = %s",
                (plan['id'], plan['id']),
            )
            result = cursor.fetchone()
            wyk = result['total'] if result and result['total'] is not None else plan['tonaz_rzeczywisty'] or 0
            plan['tonaz_rzeczywisty'] = wyk
            suma_wyk_agro += wyk
        suma_minut_plan_agro += dur

        cursor.execute(
            f"SELECT pw.id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania FROM {t_pa_agro} pw JOIN {t_pp_agro} pp ON pw.plan_id = pp.id WHERE pp.data_planu = %s AND pp.produkt = %s AND pp.sekcja = 'Workowanie' ORDER BY pw.id DESC",
            (wybrana_data, plan['produkt']),
        )
        palety_rows = cursor.fetchall()
        palety_mapa[plan['id']] = [
            (
                row['waga'],
                (row['data_dodania'].strftime('%H:%M') if hasattr(row['data_dodania'], 'strftime') else str(row['data_dodania'])),
                row['tara'],
                row['waga_brutto'],
            )
            for row in palety_rows
        ]

    return {
        'plany_agro': plany_agro,
        'palety_mapa': palety_mapa,
        'suma_plan_agro': suma_plan_agro,
        'suma_wyk_agro': suma_wyk_agro,
        'suma_minut_plan_agro': suma_minut_plan_agro,
    }


def build_panel_summary_context(
    cursor,
    wybrana_data,
    aktywna_zakladka,
    wybrana_linia,
    table_plan,
    plany_list,
    plany_agro,
    suma_plan,
    suma_wyk,
    suma_minut_plan,
    suma_plan_agro,
    suma_wyk_agro,
):
    """Build settlement rows and final quality/incomplete metrics for planista panel."""
    rozliczenia = []
    cur_tab_line = 'AGRO' if aktywna_zakladka == 'agro' else 'PSD'
    cur_tab_plany = plany_agro if aktywna_zakladka == 'agro' else plany_list
    t_sz_r = get_table_name('szarze', cur_tab_line)
    t_ds_r = get_table_name('dosypki', cur_tab_line)
    t_pa_r = get_table_name('palety_workowanie', cur_tab_line)
    t_bf_r = get_table_name('bufor', cur_tab_line)
    t_pp_r = get_table_name('plan_produkcji', cur_tab_line)

    for plan in cur_tab_plany:
        if plan['sekcja'].lower() != 'zasyp':
            continue

        zasyp_id = plan['id']
        produkt = plan['produkt']
        planowany_zasyp = plan['tonaz'] or 0
        cursor.execute(
            f"SELECT (COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM {t_ds_r} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0)) as total FROM {t_sz_r} WHERE plan_id = %s",
            (zasyp_id, zasyp_id),
        )
        zasyp_kg = cursor.fetchone()['total'] or 0
        cursor.execute(
            f"SELECT COALESCE(SUM(CASE WHEN waga_potwierdzona > 0 THEN waga_potwierdzona ELSE waga END), 0) as total FROM {t_pa_r} WHERE plan_id IN (SELECT id FROM {t_pp_r} WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie' AND produkt = %s)",
            (wybrana_data, produkt),
        )
        spakowano_palety = cursor.fetchone()['total'] or 0
        cursor.execute(
            f"SELECT SUM(tonaz_rzeczywisty - spakowano) as total FROM {t_bf_r} WHERE zasyp_id = %s AND data_planu = %s AND status = 'aktywny'",
            (zasyp_id, wybrana_data),
        )
        bufor_spakowano = cursor.fetchone()['total'] or 0
        cursor.execute(
            f"SELECT COALESCE(SUM(tonaz), 0) as total FROM {t_pp_r} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' AND produkt = %s",
            (wybrana_data, produkt),
        )
        plan_workowanie = cursor.fetchone()['total'] or 0
        if plan_workowanie == 0 and plan.get('linked_workowanie_tonaz'):
            plan_workowanie = plan['linked_workowanie_tonaz']

        rozliczenia.append(
            {
                'zasyp_id': zasyp_id,
                'produkt': produkt,
                'status': plan['status'],
                'planowany_zasyp': round(float(planowany_zasyp), 1),
                'zasyp_kg': round(float(zasyp_kg), 1),
                'plan_workowanie': round(float(plan_workowanie), 1),
                'spakowano_palety': round(float(spakowano_palety), 1),
                'bufor_spakowano': round(float(bufor_spakowano), 1),
                'diff_no_buf': round(float(zasyp_kg) - float(spakowano_palety), 1),
                'diff_with_buf': round(float(zasyp_kg) - (float(spakowano_palety) + float(bufor_spakowano)), 1),
            }
        )

    procent = (suma_wyk / suma_plan * 100) if suma_plan > 0 else 0
    procent_agro = (suma_wyk_agro / suma_plan_agro * 100) if suma_plan_agro > 0 else 0
    procent_czasu = (suma_minut_plan / 450 * 100)

    cursor.execute(
        f"SELECT id, produkt, tonaz, sekcja, status FROM {table_plan} WHERE data_planu=%s AND (COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc') AND status != 'zakonczone' ORDER BY id DESC",
        (wybrana_data,),
    )
    quality_orders = cursor.fetchall()
    quality_count = len(quality_orders)

    has_incomplete_psd = any(
        plan['status'] == 'zakonczone' and (plan['tonaz_rzeczywisty'] or 0) < (plan['tonaz'] or 0)
        for plan in plany_list
    )
    has_incomplete_agro = any(
        plan['status'] == 'zakonczone' and (plan['tonaz_rzeczywisty'] or 0) < (plan['tonaz'] or 0)
        for plan in plany_agro
    )
    if not has_incomplete_psd:
        t_p_chk = get_table_name('plan_produkcji', 'PSD')
        cursor.execute(
            f"SELECT COUNT(*) as cnt FROM {t_p_chk} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' AND status = 'zakonczone' AND COALESCE(tonaz_rzeczywisty, 0) < COALESCE(tonaz, 0)",
            (wybrana_data,),
        )
        if cursor.fetchone()['cnt'] > 0:
            has_incomplete_psd = True
    if not has_incomplete_agro:
        t_p_chk = get_table_name('plan_produkcji', 'AGRO')
        cursor.execute(
            f"SELECT COUNT(*) as cnt FROM {t_p_chk} WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' AND status = 'zakonczone' AND COALESCE(tonaz_rzeczywisty, 0) < COALESCE(tonaz, 0)",
            (wybrana_data,),
        )
        if cursor.fetchone()['cnt'] > 0:
            has_incomplete_agro = True
    has_incomplete_plans = has_incomplete_psd or has_incomplete_agro

    return {
        'rozliczenia': rozliczenia,
        'procent': procent,
        'procent_agro': procent_agro,
        'procent_czasu': procent_czasu,
        'quality_orders': quality_orders,
        'quality_count': quality_count,
        'has_incomplete_plans': has_incomplete_plans,
        'has_incomplete_psd': has_incomplete_psd,
        'has_incomplete_agro': has_incomplete_agro,
    }


def build_bufor_banner_context(cursor, wybrana_data, wybrana_linia):
    """Build previous-day active buffer reminder banner for planista panel."""
    bufor_remaining = []
    bufor_source_date = None
    bufor_source_date_fmt = None
    t_bf_now = get_table_name('bufor', wybrana_linia)
    now_time = _dt.now().time()
    show_bufor_banner = (now_time <= _time(7, 30)) or (wybrana_data != _date.today().strftime('%Y-%m-%d'))

    if show_bufor_banner:
        cursor.execute(
            f"SELECT produkt, SUM(COALESCE(tonaz_rzeczywisty, 0) - COALESCE(spakowano, 0)) as pozostalo FROM {t_bf_now} WHERE status = 'aktywny' AND data_planu = DATE_SUB(%s, INTERVAL 1 DAY) GROUP BY produkt HAVING pozostalo > 0",
            (wybrana_data,),
        )
        bufor_remaining = [
            {'produkt': row['produkt'], 'pozostalo_kg': round(float(row['pozostalo']), 1)}
            for row in cursor.fetchall()
        ]
        if bufor_remaining:
            juz_przeniesione = set()
            for linia_chk in ['PSD', 'AGRO']:
                t_pp_chk = get_table_name('plan_produkcji', linia_chk)
                try:
                    produkty_buf = [row['produkt'] for row in bufor_remaining]
                    fmt_buf = ','.join(['%s'] * len(produkty_buf))
                    cursor.execute(
                        f"SELECT DISTINCT produkt FROM {t_pp_chk} "
                        f"WHERE DATE(data_planu) = %s AND COALESCE(typ_zlecenia,'') = 'carry_over_ghost' "
                        f"AND produkt IN ({fmt_buf})",
                        [wybrana_data] + produkty_buf,
                    )
                    for row in cursor.fetchall():
                        juz_przeniesione.add((row['produkt'] or '').strip().lower())
                except Exception:
                    pass
            bufor_remaining = [
                row for row in bufor_remaining if (row['produkt'] or '').strip().lower() not in juz_przeniesione
            ]
        if bufor_remaining:
            bufor_source_date = str((_dt.strptime(wybrana_data, '%Y-%m-%d') - _timedelta(days=1)).date())
            bufor_source_date_fmt = _dt.strptime(bufor_source_date, '%Y-%m-%d').strftime('%d.%m.%Y')

    return {
        'bufor_remaining': bufor_remaining,
        'bufor_source_date': bufor_source_date,
        'bufor_source_date_fmt': bufor_source_date_fmt,
    }