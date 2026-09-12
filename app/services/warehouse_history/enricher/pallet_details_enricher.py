import json
from app.services.warehouse_history.enricher.product_validator import ProductValidator

class PalletDetailsEnricher:
    """Service responsible for enriching pallet product names, weights, and SSCC from warehouse tables."""

    @classmethod
    def extract_from_delivery_item(cls, d_it: dict) -> tuple[str, float, str, str]:
        """Extract name, weight, SSCC, and pallet_id from a delivery item dictionary."""
        if not isinstance(d_it, dict):
            return '', 0.0, '', ''
        w_val = 0.0
        for w_key in ('netWeight', 'quantity', 'unitsPerPallet', 'waga_netto', 'wagaNetto', 'ilosc', 'waga', 'currentWeight', 'weight'):
            raw_val = d_it.get(w_key)
            if raw_val is not None:
                try:
                    f_val = float(raw_val)
                    if f_val > 0:
                        w_val = f_val
                        break
                except (ValueError, TypeError):
                    pass
        n_val = ''
        for n_key in ('productName', 'product_name', 'nazwa', 'surowiec', 'produkt', 'name'):
            cand = str(d_it.get(n_key) or '').strip()
            if cand and cand.lower() not in ProductValidator.GENERIC_NAMES:
                n_val = cand
                break
        nr_val = ''
        for nr_key in ('nr_palety', 'nrPalety', 'pallet_sscc', 'sscc'):
            cand = str(d_it.get(nr_key) or '').strip()
            if cand and cand != '-':
                nr_val = cand
                break
        p_id = str(d_it.get('sourcePalletId') or d_it.get('pallet_id') or d_it.get('id') or '').strip()
        return n_val, w_val, nr_val, p_id

    @classmethod
    def enrich_unresolved_pallets(cls, cursor, items: list[dict], has_pa: bool, has_pw: bool) -> None:
        """Fetch missing pallet details via SSCC, ID, and delivery history."""
        unresolved = [
            x for x in items
            if ProductValidator.is_invalid_product_name(x.get('nazwa'))
            or not x.get('nr_palety')
            or x['nr_palety'] == '-'
            or float(x.get('ilosc') or 0.0) == 0.0
        ]
        if not unresolved:
            cls.propagate_known_names(items)
            return

        sscc_map = {}
        id_map = {}
        sscc_candidates = list(set([x['nr_palety'] for x in unresolved if x.get('nr_palety') and x['nr_palety'] != '-']))

        if sscc_candidates:
            cls._populate_sscc_map(cursor, sscc_candidates, sscc_map, has_pa, has_pw)

        still_unresolved = [x for x in unresolved if x.get('paleta_id')]
        id_candidates = list(set([int(x['paleta_id']) for x in still_unresolved if str(x['paleta_id']).isdigit()]))
        if id_candidates:
            cls._populate_id_map(cursor, id_candidates, id_map, has_pa, has_pw)

        for item in items:
            p_nr = item.get('nr_palety')
            if p_nr in sscc_map:
                s_nazwa, s_waga = sscc_map[p_nr]
                if ProductValidator.is_invalid_product_name(item.get('nazwa')) and not ProductValidator.is_invalid_product_name(s_nazwa):
                    item['nazwa'] = s_nazwa
                if item['ilosc'] == 0.0 and s_waga > 0:
                    item['ilosc'] = s_waga

            p_id = int(item['paleta_id']) if str(item.get('paleta_id') or '').isdigit() else None
            if p_id:
                pref_keys = [
                    ('magazyn_palety_agro_fk', p_id), ('palety_agro', p_id), ('magazyn_palety_agro', p_id),
                    ('magazyn_agro_surowce', p_id), ('magazyn_palety_fk', p_id), ('palety_workowanie', p_id),
                    ('magazyn_palety', p_id), ('magazyn_surowce', p_id), ('magazyn_agro_opakowania', p_id),
                    ('magazyn_opakowania', p_id), ('magazyn_archiwum', p_id)
                ]
                for k in pref_keys:
                    if k in id_map:
                        r_nazwa, r_waga, r_nr = id_map[k]
                        if ProductValidator.is_invalid_product_name(item.get('nazwa')) and not ProductValidator.is_invalid_product_name(r_nazwa):
                            item['nazwa'] = r_nazwa
                        if item['ilosc'] == 0.0 and r_waga > 0:
                            item['ilosc'] = r_waga
                        if (not item.get('nr_palety') or item['nr_palety'] == '-') and r_nr:
                            item['nr_palety'] = r_nr
                        break

        cls._enrich_from_deliveries(cursor, items)
        cls.propagate_known_names(items)

    @classmethod
    def _populate_sscc_map(cls, cursor, cands: list[str], sscc_map: dict, has_pa: bool, has_pw: bool):
        def check_table(tbl, name_col, w_col, sub_cands):
            if not sub_cands: return
            ph = ', '.join(['%s'] * len(sub_cands))
            try:
                cursor.execute(f"SELECT nr_palety, {name_col} as nazwa, {w_col} as waga FROM {tbl} WHERE nr_palety IN ({ph})", tuple(sub_cands))
                for m in cursor.fetchall() or []:
                    nr = m.get('nr_palety')
                    if nr:
                        w, n = float(m.get('waga') or 0.0), str(m.get('nazwa') or '').strip()
                        pn, pw = sscc_map.get(nr, ('', 0.0))
                        sscc_map[nr] = (pn if (pn and pn.lower() not in ProductValidator.GENERIC_NAMES) else n, pw if pw > 0 else w)
            except Exception: pass

        if has_pa:
            check_table('magazyn_palety_agro', 'produkt', 'waga_netto', cands)
            check_table('palety_agro', 'produkt', 'waga', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        if has_pw:
            check_table('magazyn_palety', 'produkt', 'waga_netto', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        check_table('magazyn_agro_surowce', 'nazwa', 'stan_magazynowy', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        check_table('magazyn_surowce', 'nazwa', 'stan_magazynowy', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        check_table('magazyn_agro_opakowania', 'nazwa', 'stan_magazynowy', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        check_table('magazyn_opakowania', 'nazwa', 'stan_magazynowy', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        check_table('magazyn_dodatki', 'nazwa', 'stan_magazynowy', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])
        check_table('magazyn_archiwum', 'nazwa', 'waga_ostatnia', [s for s in cands if s not in sscc_map or sscc_map[s][1] == 0.0])

    @classmethod
    def _populate_id_map(cls, cursor, cands: list[int], id_map: dict, has_pa: bool, has_pw: bool):
        ph = ', '.join(['%s'] * len(cands))
        queries = [
            ('magazyn_palety_agro_fk', f"SELECT paleta_workowanie_id as p_id, nr_palety, produkt as nazwa, waga_netto as waga FROM magazyn_palety_agro WHERE paleta_workowanie_id IN ({ph})"),
            ('magazyn_palety_agro', f"SELECT id as p_id, nr_palety, produkt as nazwa, waga_netto as waga FROM magazyn_palety_agro WHERE id IN ({ph})"),
            ('magazyn_agro_surowce', f"SELECT id as p_id, nr_palety, nazwa, stan_magazynowy as waga FROM magazyn_agro_surowce WHERE id IN ({ph})"),
            ('magazyn_palety_fk', f"SELECT paleta_workowanie_id as p_id, nr_palety, produkt as nazwa, waga_netto as waga FROM magazyn_palety WHERE paleta_workowanie_id IN ({ph})"),
            ('magazyn_palety', f"SELECT id as p_id, nr_palety, produkt as nazwa, waga_netto as waga FROM magazyn_palety WHERE id IN ({ph})"),
            ('magazyn_surowce', f"SELECT id as p_id, nr_palety, nazwa, stan_magazynowy as waga FROM magazyn_surowce WHERE id IN ({ph})"),
            ('magazyn_archiwum', f"SELECT original_id as p_id, nr_palety, nazwa, waga_ostatnia as waga FROM magazyn_archiwum WHERE original_id IN ({ph})"),
            ('magazyn_opakowania', f"SELECT id as p_id, nr_palety, nazwa, stan_magazynowy as waga FROM magazyn_opakowania WHERE id IN ({ph})"),
            ('magazyn_agro_opakowania', f"SELECT id as p_id, nr_palety, nazwa, stan_magazynowy as waga FROM magazyn_agro_opakowania WHERE id IN ({ph})")
        ]
        if has_pa:
            queries.insert(2, ('palety_agro', f"SELECT pa.id as p_id, pa.nr_palety, ppa.produkt as nazwa, COALESCE(NULLIF(pa.waga_potwierdzona, 0), pa.waga) as waga FROM palety_agro pa LEFT JOIN plan_produkcji_agro ppa ON pa.plan_id = ppa.id WHERE pa.id IN ({ph})"))
        if has_pw:
            queries.insert(5, ('palety_workowanie', f"SELECT pw.id as p_id, pw.nr_palety, pp.produkt as nazwa, COALESCE(NULLIF(pw.waga_potwierdzona, 0), pw.waga) as waga FROM palety_workowanie pw LEFT JOIN plan_produkcji pp ON pw.plan_id = pp.id WHERE pw.id IN ({ph})"))

        for key_prefix, q in queries:
            try:
                cursor.execute(q, tuple(cands))
                for m in cursor.fetchall() or []:
                    if m.get('p_id'):
                        id_map[(key_prefix, m['p_id'])] = (m.get('nazwa'), float(m.get('waga') or 0.0), m.get('nr_palety'))
            except Exception: pass

    @classmethod
    def _enrich_from_deliveries(cls, cursor, items: list[dict]):
        unresolved = [x for x in items if float(x.get('ilosc') or 0.0) == 0.0 or ProductValidator.is_invalid_product_name(x.get('nazwa'))]
        for item in unresolved:
            nr_p = str(item.get('nr_palety') or '').strip()
            p_id = str(item.get('paleta_id') or '').strip()
            clauses, params = [], []
            if nr_p and nr_p != '-': clauses.append("items LIKE %s"); params.append(f"%{nr_p}%")
            if p_id and p_id.isdigit(): clauses.append("items LIKE %s"); params.append(f"%{p_id}%")
            if not clauses: continue
            try:
                cursor.execute(f"SELECT items FROM magazyn_dostawy WHERE {' OR '.join(clauses)} ORDER BY id DESC LIMIT 5", tuple(params))
                for d_row in cursor.fetchall() or []:
                    d_items = json.loads(d_row.get('items')) if isinstance(d_row.get('items'), str) else (d_row.get('items') or [])
                    if isinstance(d_items, list):
                        for d_it in d_items:
                            d_name, d_w, d_nr, d_pid = cls.extract_from_delivery_item(d_it)
                            if (nr_p and nr_p != '-' and d_nr == nr_p) or (p_id and d_pid == p_id):
                                if ProductValidator.is_invalid_product_name(item.get('nazwa')) and not ProductValidator.is_invalid_product_name(d_name):
                                    item['nazwa'] = d_name
                                if item['ilosc'] == 0.0 and d_w > 0:
                                    item['ilosc'] = d_w
                                if (not item.get('nr_palety') or item['nr_palety'] == '-') and d_nr:
                                    item['nr_palety'] = d_nr
                                break
                    if item['ilosc'] > 0 and not ProductValidator.is_invalid_product_name(item.get('nazwa')):
                        break
            except Exception: pass

    @classmethod
    def propagate_known_names(cls, items: list[dict]):
        pallet_known_names = {}
        for x in items:
            p_nr, p_n = x.get('nr_palety'), x.get('nazwa')
            if p_nr and p_nr != '-' and not ProductValidator.is_invalid_product_name(p_n):
                pallet_known_names.setdefault(p_nr, p_n)
        for x in items:
            p_nr = x.get('nr_palety')
            if p_nr and p_nr in pallet_known_names and ProductValidator.is_invalid_product_name(x.get('nazwa')):
                x['nazwa'] = pallet_known_names[p_nr]
