import re
from datetime import datetime
from app.services.warehouse_history.history_indexer import HistoryIndexer
from app.services.warehouse_history.enricher.product_validator import ProductValidator
from app.services.warehouse_history.enricher.movement_classifier import MovementClassifier
from app.services.warehouse_history.enricher.location_route_resolver import LocationRouteResolver
from app.services.warehouse_history.enricher.pallet_details_enricher import PalletDetailsEnricher
from app.services.warehouse_history.enricher.order_details_enricher import OrderDetailsEnricher
from app.services.warehouse_history.enricher.history_deduplicator import HistoryDeduplicator

class HistoryEnricherService:
    """Orchestrator service for enriching and deduplicating warehouse movement records."""

    @staticmethod
    def parse_dt(r):
        """Backwards-compatible wrapper for parsing row datetime."""
        return MovementClassifier.parse_dt(r)

    @staticmethod
    def get_canonical_type(typ_str, comment=''):
        """Backwards-compatible wrapper for canonical movement category."""
        return MovementClassifier.get_canonical_type(typ_str, comment)

    @staticmethod
    def is_invalid_product_name(cand) -> bool:
        """Backwards-compatible wrapper for product name validation."""
        return ProductValidator.is_invalid_product_name(cand)

    @classmethod
    def enrich_and_filter_history(
        cls, cursor, all_rows: list[dict], linia: str, surowiec: str | None,
        stacja: str | None, typ_operacji: str | None, limit: int
    ) -> list[dict]:
        """Orchestrate pipeline: route resolution, data enrichment, order attachment, and deduplication."""
        has_pw = bool(HistoryIndexer.get_table_columns(cursor, 'palety_workowanie'))
        has_pa = bool(HistoryIndexer.get_table_columns(cursor, 'palety_agro'))

        # 1. Resolve chronological routes and collect deduplication signatures
        LocationRouteResolver.resolve_routes_chronological(all_rows)
        rec_sigs, split_sigs = HistoryDeduplicator.extract_reception_and_split_signatures(all_rows)

        # 2. Build initial candidate items from newest to oldest
        all_rows.sort(key=MovementClassifier.parse_dt, reverse=True)
        seen_dict = {}

        for r in all_rows:
            item = cls._build_candidate_item(r, rec_sigs, split_sigs)
            if not item:
                continue

            dt_key = item['data']
            nr_p = item['nr_palety']
            p_ident = nr_p if (nr_p and nr_p != '-') else (f"id_{item.get('paleta_id')}" if item.get('paleta_id') else f"row_{item.get('id')}")
            key = f"{dt_key}_{p_ident}_{item['typ']}_{item['user']}"

            if key in seen_dict:
                cls._merge_initial_item(seen_dict[key], item)
            else:
                seen_dict[key] = item

        candidates = list(seen_dict.values())

        # 3. Filter by operation type
        if typ_operacji and typ_operacji != 'ALL':
            candidates = [x for x in candidates if MovementClassifier.matches_operation_type(x, typ_operacji)]

        result_slice = candidates[:limit]

        # 4. Enrich missing pallet attributes (product names, weights, SSCC)
        PalletDetailsEnricher.enrich_unresolved_pallets(cursor, result_slice, has_pa, has_pw)

        # 5. Attach production order / plan details and routing for creations and deletions
        OrderDetailsEnricher.attach_production_orders(cursor, result_slice)

        # 6. Filter by search query (surowiec/sscc/comment)
        if surowiec:
            s_query = surowiec.strip().lower()
            result_slice = [
                x for x in result_slice
                if s_query in (x.get('nazwa') or '').lower()
                or s_query in (x.get('nr_palety') or '').lower()
                or s_query in (x.get('komentarz') or '').lower()
            ]

        # 7. Final canonical deduplication pass
        return HistoryDeduplicator.deduplicate_canonical_pass(result_slice)

    @classmethod
    def _build_candidate_item(cls, r: dict, rec_sigs: set, split_sigs: set) -> dict | None:
        """Construct and sanitize an enriched movement item dictionary."""
        dt = MovementClassifier.parse_dt(r)
        dt_key = dt.strftime('%Y-%m-%d %H:%M') if dt != datetime.min else '-'
        koment = str(r.get('komentarz') or '').strip()
        stacja_val = r.get('_stacja_val') or r.get('lokalizacja_docelowa') or r.get('lokalizacja_zrodlowa') or '-'
        src_loc = r.get('_src_loc') or r.get('lokalizacja_zrodlowa') or '-'
        dst_loc = r.get('_dst_loc') or r.get('lokalizacja_docelowa') or '-'

        nr_p_val = r.get('nr_palety') or ''
        if not nr_p_val or nr_p_val == '-':
            if koment:
                m_sscc = re.search(r'\b(SUR\d{6,20}|AGR\d{6,20}|PSD\d{6,20}|\d{18,20})\b', koment)
                if m_sscc:
                    nr_p_val = m_sscc.group(1)

        if HistoryDeduplicator.is_phantom_dispatch(r, dt_key, nr_p_val, dst_loc, rec_sigs):
            return None
        if HistoryDeduplicator.is_split_shadow(r, dt_key, nr_p_val, split_sigs):
            return None

        typ_display = r.get('typ_ruchu') or '-'
        if typ_display == 'WYDANIE_PRZESUNIECIE':
            typ_display = 'PRZESUNIECIE'

        nazwa_val = cls._extract_initial_product_name(r, koment)
        ilosc_val = cls._extract_initial_quantity(r, koment)
        stacja_val, src_loc, dst_loc = cls._normalize_station_display(r, stacja_val, src_loc, dst_loc, koment, typ_display)

        return {
            'id': r['id'],
            'paleta_id': r.get('paleta_id'),
            'typ_palety': r.get('typ_palety'),
            'data': dt_key,
            'linia': r.get('linia_ruch') or 'PSD',
            'stacja': stacja_val,
            'skad': src_loc or '-',
            'dokad': dst_loc or '-',
            'nazwa': nazwa_val or '-',
            'nr_palety': nr_p_val or '-',
            'ilosc': ilosc_val,
            'typ': typ_display,
            'user': r.get('autor_login') or '-',
            'komentarz': koment or '-'
        }

    @classmethod
    def _extract_initial_product_name(cls, r: dict, koment: str) -> str:
        nazwa_val = r.get('surowiec_nazwa') or ''
        if not nazwa_val or nazwa_val.lower() in ProductValidator.GENERIC_LOCATION_NAMES:
            if koment:
                m_wg = re.search(r'(?:przyjęcie wg|przyjecie wg|wg):\s*([^,;->\(\)]+)', koment, re.IGNORECASE)
                if m_wg and m_wg.group(1).strip().lower() not in ProductValidator.GENERIC_LOCATION_NAMES:
                    nazwa_val = m_wg.group(1).strip()
                if not nazwa_val or nazwa_val.lower() in ProductValidator.GENERIC_LOCATION_NAMES:
                    m_prod = re.search(r'(?:paletę|paleta|surowiec|surowca|produkt|towar|materiał|material):\s*([^,;->\(\)]+)', koment, re.IGNORECASE)
                    if m_prod and not ProductValidator.is_invalid_product_name(m_prod.group(1)):
                        nazwa_val = m_prod.group(1).strip()
                    elif re.search(r'(?:Utworzono paletę|Przeklasyfikowano na surowiec):\s*([^,;->\(\)]+)', koment, re.IGNORECASE):
                        m_p2 = re.search(r'(?:Utworzono paletę|Przeklasyfikowano na surowiec):\s*([^,;->\(\)]+)', koment, re.IGNORECASE)
                        if not ProductValidator.is_invalid_product_name(m_p2.group(1)):
                            nazwa_val = m_p2.group(1).strip()
                    elif re.search(r'\(([^\)]*(?:mączka|kreda|sól|sol|śruta|sruta|otręby|otreby|premix|premiks|wit|kukurydz|pszenic|soj|rzepak|drożdż|drozdz|tłuszcz|tluszcz|wapno|olej|fosfor|kwas|melas|karm|dodatek|witamina)[^\)]*)\)', koment, re.IGNORECASE):
                        m_br = re.search(r'\(([^\)]*(?:mączka|kreda|sól|sol|śruta|sruta|otręby|otreby|premix|premiks|wit|kukurydz|pszenic|soj|rzepak|drożdż|drozdz|tłuszcz|tluszcz|wapno|olej|fosfor|kwas|melas|karm|dodatek|witamina)[^\)]*)\)', koment, re.IGNORECASE)
                        cand = m_br.group(1).split(',')[0].strip()
                        if not ProductValidator.is_invalid_product_name(cand):
                            nazwa_val = cand
        return nazwa_val

    @classmethod
    def _extract_initial_quantity(cls, r: dict, koment: str) -> float:
        ilosc_val = float(r.get('waga_ref') or 0.0)
        typ_op = str(r.get('typ_ruchu') or '').upper()
        is_pkg = typ_op in ('ZMIANA_OPAKOWANIA', 'OPAKOWANIE', 'ZMIANA_TYPU_MATERIALU', 'ZMIANA_TYPU_MATERIALU_BULK') or 'opakowan' in koment.lower()
        if koment:
            m_kw = re.search(r'(?:ilość|ilosc|waga ost\.?|waga|stan|przeniesiono|odjęto|odjeto):\s*([\d\.]+)', koment, re.IGNORECASE)
            if m_kw:
                try: ilosc_val = float(m_kw.group(1))
                except Exception: pass
            else:
                m_arrow = re.search(r'->\s*([\d\.]+)', koment)
                if m_arrow and not is_pkg:
                    try: ilosc_val = float(m_arrow.group(1))
                    except Exception: pass
                else:
                    m_kg = re.search(r'([\d\.]+)\s*kg', koment, re.IGNORECASE)
                    if m_kg and ilosc_val == 0.0 and not is_pkg and 'worek (' not in koment.lower() and 'worek(' not in koment.lower():
                        try: ilosc_val = float(m_kg.group(1))
                        except Exception: pass
        return ilosc_val

    @classmethod
    def _normalize_station_display(cls, r: dict, stacja_val: str, src_loc: str, dst_loc: str, koment: str, typ_display: str) -> tuple[str, str, str]:
        if ('->' not in stacja_val) and koment:
            m_st = re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)\b', koment, re.IGNORECASE)
            if m_st:
                dst_st = m_st.group(1).upper()
                src_st = src_loc if (src_loc and src_loc not in ('-', 'Magazyn')) else ('MS01' if (r.get('linia_ruch') == 'AGRO') else 'MP01')
                stacja_val = f"{src_st} -> {dst_st}"
                src_loc, dst_loc = src_st, dst_st

        if any(k in koment.lower() for k in ('przyjęcie z dostawy', 'przyjecie z dostawy')) and stacja_val.startswith('DOSTAWA ->'):
            stacja_val = stacja_val.replace('DOSTAWA ->', 'OCZEKUJĄCE ->')
            src_loc = 'OCZEKUJĄCE'

        if ('->' not in stacja_val) and (any(k in typ_display.upper() for k in ('PRZYJECIE', 'PRZYJĘCIE', 'DOSTAWA', 'PW', 'PZ')) or 'dostaw' in koment.lower()):
            is_osip_row = stacja_val.upper() in ('OSIP', 'BFOS') or bool(re.match(r'^(OS\d+|A\d+)$', stacja_val, re.IGNORECASE)) or (r.get('linia_ruch') or r.get('linia') or '').upper() == 'OSIP' or 'osip' in koment.lower()
            is_from_pending = any(k in koment.lower() for k in ('przyjęcie z dostawy', 'przyjecie z dostawy')) or src_loc in ('OCZEKUJĄCE', 'OCZEKUJACE')
            target_dest = stacja_val if (stacja_val and stacja_val != '-') else ('OSIP' if is_osip_row else 'MS01')
            if is_from_pending:
                stacja_val = f"OCZEKUJĄCE -> {target_dest}"
                src_loc, dst_loc = 'OCZEKUJĄCE', target_dest
            elif is_osip_row:
                dst_os = stacja_val if stacja_val != '-' else 'OSIP'
                stacja_val = f"DOSTAWA -> {dst_os}"
                src_loc, dst_loc = 'DOSTAWA', dst_os
            elif stacja_val != '-':
                stacja_val = f"DOSTAWA -> {stacja_val}"
                src_loc = 'DOSTAWA'
                dst_loc = stacja_val.split('->')[1].strip()
        elif stacja_val == '-' and koment:
            m_st = re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*|MGW\d*|Workowanie\s+\w+)\b', koment, re.IGNORECASE)
            if m_st:
                stacja_val = m_st.group(1).upper()

        return stacja_val, src_loc, dst_loc

    @classmethod
    def _merge_initial_item(cls, existing: dict, current: dict):
        nr_p_val = current.get('nr_palety')
        nazwa_val = current.get('nazwa')
        stacja_val = current.get('stacja')
        ilosc_val = current.get('ilosc', 0.0)

        if (not existing.get('nr_palety') or existing['nr_palety'] == '-') and (nr_p_val and nr_p_val != '-'):
            existing['nr_palety'] = nr_p_val
        if (not existing.get('nazwa') or existing['nazwa'] in ('-', 'Surowiec', 'Surowiec AGRO')) and (nazwa_val and nazwa_val not in ('-', 'Surowiec', 'Surowiec AGRO')):
            existing['nazwa'] = nazwa_val
        if '->' in str(stacja_val) and '->' not in str(existing.get('stacja')):
            existing['stacja'] = stacja_val
            existing['skad'] = current.get('skad')
            existing['dokad'] = current.get('dokad')
        if existing.get('ilosc', 0.0) == 0.0 and ilosc_val > 0:
            existing['ilosc'] = ilosc_val
