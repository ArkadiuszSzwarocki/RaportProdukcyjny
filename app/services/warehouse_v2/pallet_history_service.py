import re
import json
from datetime import datetime
from app.db import get_db_connection

class PalletHistoryService:
    @staticmethod
    def get_pallet_history(pallet_id, pallet_type, linia='PSD', sscc=None):
        """Fetch comprehensive pallet movement and lifecycle history from all sources."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            p_type_norm = str(pallet_type or '').strip().lower()
            is_finished_good = not any(k in p_type_norm for k in ('surow', 'opakow', 'dodat'))
            
            real_id = None
            nr_pal_sscc = str(sscc).strip() if sscc else None
            pw_id = None
            
            # Find identity across warehouse tables
            search_tables = []
            if is_finished_good:
                search_tables = ['magazyn_palety', 'magazyn_palety_agro']
            elif 'surow' in p_type_norm:
                search_tables = ['magazyn_surowce', 'magazyn_agro_surowce']
            elif 'opakow' in p_type_norm:
                search_tables = ['magazyn_opakowania', 'magazyn_agro_opakowania']
            else:
                search_tables = ['magazyn_dodatki']

            for tbl in search_tables:
                try:
                    cursor.execute(f"SELECT * FROM {tbl} WHERE id = %s OR nr_palety = %s LIMIT 1", (pallet_id, str(pallet_id)))
                    row_found = cursor.fetchone()
                    if row_found:
                        real_id = row_found.get('id')
                        if not nr_pal_sscc and row_found.get('nr_palety'):
                            nr_pal_sscc = row_found.get('nr_palety')
                        if row_found.get('paleta_workowanie_id'):
                            pw_id = row_found.get('paleta_workowanie_id')
                        break
                except Exception:
                    pass

            target_id = real_id if real_id is not None else pallet_id
            target_sscc = nr_pal_sscc if nr_pal_sscc else str(pallet_id)

            id_candidates = []
            if target_id is not None:
                id_candidates.append(target_id)
            if real_id is not None and real_id not in id_candidates:
                id_candidates.append(real_id)

            # Resolve all pallet IDs associated with this SSCC across warehouse inventory
            if target_sscc:
                for tbl in search_tables:
                    try:
                        cursor.execute(f"SELECT id FROM {tbl} WHERE nr_palety = %s", (target_sscc,))
                        for r_row in cursor.fetchall():
                            rid = r_row.get('id')
                            if rid is not None and rid not in id_candidates:
                                id_candidates.append(rid)
                    except Exception:
                        pass
            
            id_ph_clause = "paleta_id = -1"
            if id_candidates:
                placeholders = ', '.join(['%s'] * len(id_candidates))
                id_ph_clause = f"paleta_id IN ({placeholders})"

            type_params = []
            if is_finished_good:
                type_filter_clause = "(typ_palety IN (%s, %s, %s, %s) OR typ_palety IS NULL OR typ_palety = '')"
                type_params = ['wyrob_gotowy', 'wyrób gotowy', 'polprodukt', 'półprodukt']
            elif 'surow' in p_type_norm:
                type_filter_clause = "(typ_palety = %s OR typ_palety IS NULL OR typ_palety = '')"
                type_params = ['surowiec']
            elif 'opakow' in p_type_norm:
                type_filter_clause = "(typ_palety = %s OR typ_palety IS NULL OR typ_palety = '')"
                type_params = ['opakowanie']
            else:
                type_filter_clause = "(typ_palety = %s OR typ_palety IS NULL OR typ_palety = '')"
                type_params = ['dodatek']

            # 1. Fetch from palety_historia strictly by SSCC (nr_palety)
            if target_sscc:
                sql_q = f"""
                    SELECT id, akcja as typ_ruchu, komentarz, user_login as autor_login, data_ruchu as autor_data,
                           lokalizacja_zrodlowa, lokalizacja_docelowa
                    FROM palety_historia
                    WHERE {type_filter_clause} AND (
                        nr_palety = %s OR komentarz LIKE %s
                    )
                    ORDER BY data_ruchu DESC
                """
                cursor.execute(sql_q, tuple(type_params + [target_sscc, f"%{target_sscc}%"]))
            else:
                sql_q = f"""
                    SELECT id, akcja as typ_ruchu, komentarz, user_login as autor_login, data_ruchu as autor_data,
                           lokalizacja_zrodlowa, lokalizacja_docelowa
                    FROM palety_historia
                    WHERE {type_filter_clause} AND {id_ph_clause}
                    ORDER BY data_ruchu DESC
                """
                cursor.execute(sql_q, tuple(type_params + list(id_candidates)))
            historia_nowa = cursor.fetchall() or []

            # 2. Fetch from legacy movement tables (magazyn_ruch / magazyn_agro_ruch)
            historia_stara = []
            if not is_finished_good:
                for t_ruch in ['magazyn_ruch', 'magazyn_agro_ruch']:
                    try:
                        if target_sscc:
                            cursor.execute(f"""
                                SELECT id, typ_ruchu, autor_login, COALESCE(autor_data, created_at) as autor_data, komentarz,
                                       NULL as lokalizacja_zrodlowa, lokalizacja as lokalizacja_docelowa
                                FROM {t_ruch} 
                                WHERE komentarz LIKE %s
                                ORDER BY id DESC
                            """, (f"%{target_sscc}%",))
                        elif id_candidates:
                            cursor.execute(f"""
                                SELECT id, typ_ruchu, autor_login, COALESCE(autor_data, created_at) as autor_data, komentarz,
                                       NULL as lokalizacja_zrodlowa, lokalizacja as lokalizacja_docelowa
                                FROM {t_ruch} 
                                WHERE surowiec_id IN ({', '.join(['%s'] * len(id_candidates))})
                                ORDER BY id DESC
                            """, tuple(id_candidates))
                        historia_stara.extend(cursor.fetchall() or [])
                    except Exception:
                        pass

            # 3. Fetch finished goods confirmation events strictly by SSCC
            if is_finished_good:
                for t_pal in ['magazyn_palety', 'magazyn_palety_agro']:
                    try:
                        if target_sscc:
                            cursor.execute(f"""
                                SELECT data_potwierdzenia as autor_data, user_login as autor_login, 'POTWIERDZENIE' as typ_ruchu,
                                       CONCAT('Rejestracja wyrobu (oczekuje na przyjęcie)', IF(lokalizacja IS NOT NULL AND lokalizacja != '' AND lokalizacja != 'OCZEKUJĄCE', CONCAT(' -> ', lokalizacja), '')) as komentarz,
                                       'Produkcja' as lokalizacja_zrodlowa, COALESCE(NULLIF(lokalizacja, ''), 'OCZEKUJĄCE') as lokalizacja_docelowa
                                FROM {t_pal} 
                                WHERE nr_palety = %s AND data_potwierdzenia IS NOT NULL
                            """, (target_sscc,))
                        elif id_candidates:
                            cursor.execute(f"""
                                SELECT data_potwierdzenia as autor_data, user_login as autor_login, 'POTWIERDZENIE' as typ_ruchu,
                                       CONCAT('Rejestracja wyrobu (oczekuje na przyjęcie)', IF(lokalizacja IS NOT NULL AND lokalizacja != '' AND lokalizacja != 'OCZEKUJĄCE', CONCAT(' -> ', lokalizacja), '')) as komentarz,
                                       'Produkcja' as lokalizacja_zrodlowa, COALESCE(NULLIF(lokalizacja, ''), 'OCZEKUJĄCE') as lokalizacja_docelowa
                                FROM {t_pal} 
                                WHERE id IN ({', '.join(['%s'] * len(id_candidates))}) AND data_potwierdzenia IS NOT NULL
                            """, tuple(id_candidates))
                        row_c = cursor.fetchone()
                        if row_c and row_c.get('autor_data'):
                            curr_loc = (row_c.get('lokalizacja_docelowa') or '').strip()
                            if historia_nowa:
                                earliest_src = None
                                for h_n in reversed(historia_nowa):
                                    s_cand = (h_n.get('lokalizacja_zrodlowa') or '').strip()
                                    if s_cand and s_cand not in ('Produkcja', 'Zlecenie', '-'):
                                        earliest_src = s_cand
                                        break
                                default_buffer = 'MGW02' if 'agro' in t_pal else 'MGW01'
                                init_loc = earliest_src or default_buffer
                                row_c['lokalizacja_docelowa'] = init_loc
                                row_c['komentarz'] = f"Rejestracja wyrobu (przyjęcie na stan) -> {init_loc}"
                            historia_stara.append(row_c)
                    except Exception:
                        pass

                # 4. Fetch creation events from bagging / orders strictly by SSCC
                for t_work, t_plan in [('palety_workowanie', 'plan_produkcji'), ('palety_agro', 'plan_produkcji_agro')]:
                    try:
                        if target_sscc:
                            cursor.execute(f"""
                                SELECT pw.data_dodania as autor_data, pw.dodal_login as autor_login, 'UTWORZENIE' as typ_ruchu,
                                       CONCAT('Utworzenie palety podczas produkcji: ', COALESCE(plan.produkt, 'Wyrób gotowy'), ', waga: ', COALESCE(pw.waga, 0), ' kg') as komentarz,
                                       CONCAT('Zlecenie #', COALESCE(pw.plan_id, '-')) as lokalizacja_zrodlowa, 'BUFOR_WORKOWANIE' as lokalizacja_docelowa
                                FROM {t_work} pw
                                LEFT JOIN {t_plan} plan ON pw.plan_id = plan.id
                                WHERE pw.nr_palety = %s AND pw.data_dodania IS NOT NULL
                                LIMIT 1
                            """, (target_sscc,))
                        elif pw_id:
                            cursor.execute(f"""
                                SELECT pw.data_dodania as autor_data, pw.dodal_login as autor_login, 'UTWORZENIE' as typ_ruchu,
                                       CONCAT('Utworzenie palety podczas produkcji: ', COALESCE(plan.produkt, 'Wyrób gotowy'), ', waga: ', COALESCE(pw.waga, 0), ' kg') as komentarz,
                                       CONCAT('Zlecenie #', COALESCE(pw.plan_id, '-')) as lokalizacja_zrodlowa, 'BUFOR_WORKOWANIE' as lokalizacja_docelowa
                                FROM {t_work} pw
                                LEFT JOIN {t_plan} plan ON pw.plan_id = plan.id
                                WHERE pw.id = %s AND pw.data_dodania IS NOT NULL
                                LIMIT 1
                            """, (pw_id,))
                        row_w = cursor.fetchone()
                        if row_w and row_w.get('autor_data'):
                            historia_stara.append(row_w)
                    except Exception:
                        pass

            # 5. Fetch delivery creation and reception events directly from magazyn_dostawy
            historia_dostawy = []
            if not is_finished_good and target_sscc:
                try:
                    cursor.execute(
                        "SELECT id, supplier, order_ref, status, items, created_by, created_at FROM magazyn_dostawy WHERE items LIKE %s",
                        (f"%{target_sscc}%",)
                    )
                    for d_row in cursor.fetchall() or []:
                        raw_items_str = d_row.get('items') or '[]'
                        d_items = json.loads(raw_items_str) if isinstance(raw_items_str, str) else raw_items_str
                        for it in d_items:
                            if isinstance(it, dict) and it.get('nr_palety') == target_sscc:
                                p_sup = d_row.get('supplier') or 'Dostawca zewnętrzny'
                                p_wz = d_row.get('order_ref') or f"#{d_row.get('id')}"
                                p_user = it.get('accepted_by') or d_row.get('created_by') or 'system'
                                p_date = it.get('accepted_at') or d_row.get('created_at')
                                p_loc = it.get('lokalizacja_przyjecia') or 'OSIP'
                                p_name = it.get('productName') or 'Surowiec'
                                p_partia = it.get('nr_partii') or '-'
                                if it.get('accepted'):
                                    historia_dostawy.append({
                                        'typ_ruchu': 'PRZYJECIE',
                                        'autor_login': p_user,
                                        'autor_data': p_date,
                                        'lokalizacja_zrodlowa': 'OCZEKUJĄCE',
                                        'lokalizacja_docelowa': p_loc,
                                        'komentarz': f"Przyjęcie z dostawy: {p_name}, partia: {p_partia} (WZ: {p_wz})"
                                    })
                                else:
                                    historia_dostawy.append({
                                        'typ_ruchu': 'DOSTAWA_PRZYJECIE',
                                        'autor_login': d_row.get('created_by') or 'system',
                                        'autor_data': d_row.get('created_at'),
                                        'lokalizacja_zrodlowa': 'DOSTAWA',
                                        'lokalizacja_docelowa': 'OCZEKUJĄCE',
                                        'komentarz': f"Przyjęcie zewnętrzne z {p_sup} - WZ: {p_wz}"
                                    })
                except Exception:
                    pass

            combined = historia_nowa + historia_stara + historia_dostawy

            def get_dt(x):
                dt = x.get('autor_data')
                if isinstance(dt, datetime):
                    return dt
                if isinstance(dt, str):
                    try: return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                    except Exception: pass
                    try: return datetime.strptime(dt, '%Y-%m-%d %H:%M')
                    except Exception: pass
                return datetime.min

            combined.sort(key=get_dt, reverse=True)

            # Deduplicate entries
            seen = set()
            deduped = []
            for h in combined:
                dt = get_dt(h)
                t_raw = str(h.get('typ_ruchu') or '').upper().strip()
                c_raw = str(h.get('komentarz') or '').lower()
                if any(k in t_raw for k in ('PRZYJ', 'PW', 'PZ', 'POTWIERDZ', 'DOSTAWA')):
                    t_key = 'RECEPTION'
                elif any(k in t_raw for k in ('WYDA', 'PROD', 'RW', 'POBRANIE')):
                    t_key = 'DISPATCH'
                elif any(k in t_raw for k in ('PRZESUN', 'TRANSF', 'RELOKAC', 'RUCH', 'MM')):
                    t_key = 'RELOCATION'
                elif any(k in t_raw for k in ('UTWORZ',)):
                    t_key = 'CREATION'
                elif any(k in t_raw for k in ('USUN',)):
                    t_key = 'DELETION'
                else:
                    t_key = t_raw

                u_key = str(h.get('autor_login') or '').strip().lower()
                dt_key = dt.strftime('%Y-%m-%d %H:%M:%S') if dt != datetime.min else str(h.get('autor_data', ''))
                key = f"{dt_key}_{t_key}_{u_key}"
                if key not in seen:
                    seen.add(key)
                    h['autor_data'] = dt_key if dt != datetime.min else str(h.get('autor_data', ''))
                    
                    src = str(h.get('lokalizacja_zrodlowa') or '').strip()
                    dst = str(h.get('lokalizacja_docelowa') or '').strip()
                    kom_h = str(h.get('komentarz') or '').lower()

                    if is_finished_good and dst.lower() in ('magazyn', 'magazyn gotowy', 'magazyn wyrobów gotowych'):
                        dst = 'OCZEKUJĄCE'
                        h['lokalizacja_docelowa'] = dst
                        if h.get('komentarz') and 'na magazyn' in h['komentarz'].lower():
                            h['komentarz'] = h['komentarz'].replace('na magazyn', 'na OCZEKUJĄCE').replace('na Magazyn', 'na OCZEKUJĄCE')

                    # Station issuance check (BB, MZ, ZB, KO, MIX, WZ, etc.)
                    is_st_dst = bool(re.search(r'^(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)$', dst, re.IGNORECASE))
                    is_st_kom = bool(re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)\b', kom_h))
                    if is_st_dst or (t_key == 'DISPATCH' and is_st_kom):
                        if not is_st_dst:
                            m_st = re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)\b', kom_h)
                            if m_st:
                                dst = m_st.group(1).upper()
                        if not src or src in ('-', 'Magazyn', 'None'):
                            src = 'MS01' if 'AGRO' in str(h.get('linia') or '').upper() else 'MP01'
                        h['lokalizacja_zrodlowa'] = src
                        h['lokalizacja_docelowa'] = dst
                        h['stacja_trasa'] = f"{src} -> {dst}"

                    # Delivery / Reception check (including OSIP)
                    elif t_key == 'RECEPTION' or 'dostaw' in kom_h or 'przyjęcie' in kom_h or 'przyjecie' in kom_h:
                        is_osip_dst = (
                            dst.upper() == 'OSIP'
                            or dst.upper() == 'BFOS'
                            or bool(re.match(r'^(OS\d+|A\d+)$', dst, re.IGNORECASE))
                            or str(h.get('linia') or '').upper() == 'OSIP'
                            or 'osip' in kom_h
                        )

                        is_acceptance_from_pending = (
                            'przyjęcie z dostawy' in kom_h
                            or 'przyjecie z dostawy' in kom_h
                            or src in ('OCZEKUJĄCE', 'OCZEKUJACE')
                        ) and (dst not in ('OCZEKUJĄCE', 'OCZEKUJACE'))

                        is_initial_delivery = (
                            dst in ('OCZEKUJĄCE', 'OCZEKUJACE')
                            or 'zewnętrzne' in kom_h
                            or 'zewnetrzne' in kom_h
                            or 'dostawa zewnętrzna' in kom_h
                            or 'dostawa zewnetrzna' in kom_h
                        )

                        if is_acceptance_from_pending:
                            src = 'OCZEKUJĄCE'
                            dst = dst if (dst and dst != '-') else ('OSIP' if is_osip_dst else 'MS01')
                        elif is_initial_delivery:
                            src = 'DOSTAWA'
                            dst = 'OCZEKUJĄCE'
                        else:
                            if is_osip_dst:
                                dst = dst if (dst and dst != '-') else 'OSIP'
                                src = 'CENTRALA' if ('transfer' in kom_h or 'z centrali' in kom_h or 'z ms01' in kom_h) else ('OCZEKUJĄCE' if ('dostaw' in kom_h or 'przyjęcie' in kom_h or 'przyjecie' in kom_h) else 'DOSTAWA')
                            else:
                                src = src if (src and src not in ('-', 'None', 'null', 'brak', 'OCZEKUJACE', 'OCZEKUJĄCE')) else 'DOSTAWA'
                                dst = dst or 'OCZEKUJĄCE'
                        h['lokalizacja_zrodlowa'] = src
                        h['lokalizacja_docelowa'] = dst
                        h['stacja_trasa'] = f"{src} -> {dst}" if src != dst else dst

                    elif src and dst and src != dst:
                        h['stacja_trasa'] = f"{src} -> {dst}"
                    elif dst:
                        h['stacja_trasa'] = dst
                    elif src:
                        h['stacja_trasa'] = src
                    else:
                        h['stacja_trasa'] = '-'

                    deduped.append(h)

            return deduped
        finally:
            conn.close()
