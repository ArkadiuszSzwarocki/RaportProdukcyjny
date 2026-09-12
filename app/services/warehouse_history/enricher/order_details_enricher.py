import re

class OrderDetailsEnricher:
    """Service responsible for attaching production order and plan references to history events."""

    @classmethod
    def attach_production_orders(cls, cursor, items: list[dict]) -> None:
        """Query and attach production order / plan names for creation and deletion events."""
        target_items = [
            x for x in items
            if any(k in str(x.get('typ') or '').upper() for k in ('UTWORZ', 'USUN'))
            and (not x.get('stacja') or x['stacja'] in ('-', 'Magazyn', ''))
        ]
        if not target_items:
            # Ensure proper routing labels even if already having stacja
            cls._ensure_creation_deletion_routes(items)
            return

        plan_map = {}
        c_nrs = list(set([x['nr_palety'] for x in target_items if x.get('nr_palety') and x['nr_palety'] != '-']))
        c_ids = list(set([int(x['paleta_id']) for x in target_items if str(x.get('paleta_id') or '').isdigit()]))

        if c_nrs or c_ids:
            cls._query_plans_for_pallets(cursor, 'palety_agro', 'AGRO', c_nrs, c_ids, plan_map)
            cls._query_plans_for_pallets(cursor, 'magazyn_palety_agro', 'AGRO', c_nrs, c_ids, plan_map)
            cls._query_plans_for_pallets(cursor, 'palety_workowanie', 'PSD', c_nrs, c_ids, plan_map)
            cls._query_plans_for_pallets(cursor, 'magazyn_palety', 'PSD', c_nrs, c_ids, plan_map)

            if c_nrs:
                try:
                    ph_nr_l = ', '.join(['%s'] * len(c_nrs))
                    cursor.execute(f"""
                        SELECT pallet_code, reference_id, source_location
                        FROM magazyn_ruchy_unified 
                        WHERE pallet_code IN ({ph_nr_l}) AND reference_id IS NOT NULL AND TRIM(reference_id) != ''
                    """, tuple(c_nrs))
                    for m in cursor.fetchall() or []:
                        p_code = m.get('pallet_code')
                        ref_id = str(m.get('reference_id') or '').strip()
                        src_l = str(m.get('source_location') or '').upper()
                        l_code = 'AGRO' if 'AGRO' in src_l else ('PSD' if 'PSD' in src_l else 'AGRO')
                        if p_code and ref_id.isdigit():
                            plan_map[p_code] = (int(ref_id), l_code)
                except Exception: pass

            for x in target_items:
                nr_p = x.get('nr_palety')
                kom = str(x.get('komentarz') or '')
                if nr_p and nr_p not in plan_map:
                    m_zlec = re.search(r'Zlecenie\s*#?(\d+)', kom, re.IGNORECASE)
                    if m_zlec:
                        try:
                            z_id = int(m_zlec.group(1))
                            plan_map[nr_p] = (z_id, x.get('linia') or 'AGRO')
                        except Exception: pass

        plan_details_map = cls._fetch_plan_names(cursor, plan_map)

        for item in target_items:
            order_label = ''
            nr_p = item.get('nr_palety')
            p_id = item.get('paleta_id')

            if nr_p and nr_p in plan_map:
                order_label = plan_details_map.get(plan_map[nr_p], f"Zlecenie #{plan_map[nr_p][0]}")
            elif p_id and f"id_{p_id}" in plan_map:
                order_label = plan_details_map.get(plan_map[f"id_{p_id}"], f"Zlecenie #{plan_map[f'id_{p_id}'][0]}")

            if order_label:
                cur_kom = str(item.get('komentarz') or '')
                if order_label not in cur_kom:
                    item['komentarz'] = f"{cur_kom} ({order_label})" if cur_kom and cur_kom != '-' else order_label

        cls._ensure_creation_deletion_routes(items)

    @classmethod
    def _query_plans_for_pallets(cls, cursor, tbl: str, line_code: str, nr_cands: list, id_cands: list, plan_map: dict):
        clauses, params = [], []
        if nr_cands:
            clauses.append(f"nr_palety IN ({', '.join(['%s'] * len(nr_cands))})")
            params.extend(nr_cands)
        if id_cands:
            clauses.append(f"id IN ({', '.join(['%s'] * len(id_cands))})")
            params.extend(id_cands)
        if not clauses: return
        try:
            cursor.execute(f"SELECT id, nr_palety, plan_id FROM {tbl} WHERE ({' OR '.join(clauses)})", tuple(params))
            for m in cursor.fetchall() or []:
                p_id = m.get('plan_id')
                if p_id:
                    if m.get('nr_palety'): plan_map[m['nr_palety']] = (p_id, line_code)
                    if m.get('id'): plan_map[f"id_{m['id']}"] = (p_id, line_code)
        except Exception: pass

    @classmethod
    def _fetch_plan_names(cls, cursor, plan_map: dict) -> dict:
        plan_details = {}
        ids_agro = set([p[0] for p in plan_map.values() if p[1] == 'AGRO'])
        ids_psd = set([p[0] for p in plan_map.values() if p[1] == 'PSD'])
        if ids_agro:
            try:
                ph_a = ', '.join(['%s'] * len(ids_agro))
                cursor.execute(f"SELECT id, produkt, COALESCE(NULLIF(TRIM(nazwa_zlecenia), ''), produkt) as zlec_nazwa FROM plan_produkcji_agro WHERE id IN ({ph_a})", tuple(ids_agro))
                for r in cursor.fetchall() or []:
                    plan_details[(r['id'], 'AGRO')] = f"Zlecenie #{r['id']}: {r.get('zlec_nazwa') or r.get('produkt') or ''}"
            except Exception: pass
        if ids_psd:
            try:
                ph_p = ', '.join(['%s'] * len(ids_psd))
                cursor.execute(f"SELECT id, produkt, produkt as zlec_nazwa FROM plan_produkcji WHERE id IN ({ph_p})", tuple(ids_psd))
                for r in cursor.fetchall() or []:
                    plan_details[(r['id'], 'PSD')] = f"Zlecenie #{r['id']}: {r.get('zlec_nazwa') or r.get('produkt') or ''}"
            except Exception: pass
        return plan_details

    @classmethod
    def _ensure_creation_deletion_routes(cls, items: list[dict]):
        for item in items:
            typ_u = str(item.get('typ') or '').upper()
            line_nm = 'AGRO' if (item.get('linia') or '').upper() == 'AGRO' else 'PSD'
            if any(k in typ_u for k in ('UTWORZ',)):
                if not item.get('skad') or item.get('skad') == '-':
                    item['skad'] = f"Linia {line_nm}"
                if not item.get('dokad') or item.get('dokad') == '-':
                    item['dokad'] = 'OCZEKUJĄCE'
                if not item.get('stacja') or item.get('stacja') in ('-', 'Magazyn'):
                    item['stacja'] = f"{item['skad']} -> {item['dokad']}"
            elif any(k in typ_u for k in ('USUN',)):
                if not item.get('skad') or item.get('skad') == '-':
                    item['skad'] = 'OCZEKUJĄCE'
                if not item.get('dokad') or item.get('dokad') == '-':
                    item['dokad'] = 'USUNIĘCIE'
                if not item.get('stacja') or item.get('stacja') in ('-', 'Magazyn'):
                    item['stacja'] = f"{item['skad']} -> {item['dokad']}"
