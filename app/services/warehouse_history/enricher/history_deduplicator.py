import re
from datetime import datetime
from app.services.warehouse_history.enricher.movement_classifier import MovementClassifier
from app.services.warehouse_history.enricher.product_validator import ProductValidator

class HistoryDeduplicator:
    """Service responsible for deduplicating phantom exits, shadow movements, and redundant records."""

    @classmethod
    def extract_reception_and_split_signatures(cls, all_rows: list[dict]) -> tuple[set, set]:
        """Collect reception and split signatures to identify phantom dispatch rows."""
        reception_signatures = set()
        split_signatures = set()
        for r in all_rows:
            r_typ = str(r.get('typ_ruchu') or '').upper()
            r_kom = str(r.get('komentarz') or '').lower()
            dt_r = MovementClassifier.parse_dt(r)
            dt_k = dt_r.strftime('%Y-%m-%d %H:%M') if dt_r != datetime.min else '-'

            if 'PRZYJECIE' in r_typ or 'przyjęcie z dostawy' in r_kom or 'przyjecie z dostawy' in r_kom:
                u_k = str(r.get('autor_login') or '').strip().lower()
                dst_k = str(r.get('_dst_loc') or r.get('lokalizacja_docelowa') or '').strip().upper()
                reception_signatures.add((dt_k, u_k, dst_k))

            if 'PODZIAL' in r_typ or 'podział' in r_kom or 'podzial' in r_kom:
                p_id_k = r.get('nr_palety') or (f"{r.get('linia_ruch')}_{r.get('paleta_id')}" if r.get('paleta_id') else None)
                if p_id_k:
                    split_signatures.add((dt_k, str(p_id_k).strip().upper()))

        return reception_signatures, split_signatures

    @classmethod
    def is_phantom_dispatch(cls, r: dict, dt_key: str, nr_p_val: str, dst_loc: str, reception_signatures: set) -> bool:
        """Check if row is an orphaned phantom dispatch generated during delivery acceptance."""
        koment = str(r.get('komentarz') or '').lower()
        typ_op = str(r.get('typ_ruchu') or '').upper()
        if not r.get('paleta_id') and (not nr_p_val or nr_p_val == '-') and ('wydanie do przesunięcia' in koment or typ_op == 'WYDANIE_PRZESUNIECIE'):
            u_k = str(r.get('autor_login') or '').strip().lower()
            dst_k = str(dst_loc or '').strip().upper()
            return (dt_key, u_k, dst_k) in reception_signatures
        return False

    @classmethod
    def is_split_shadow(cls, r: dict, dt_key: str, nr_p_val: str, split_signatures: set) -> bool:
        """Check if row is a duplicate shadow relocation logged during a pallet split."""
        koment = str(r.get('komentarz') or '').lower()
        typ_op = str(r.get('typ_ruchu') or '').upper()
        p_id_match = str(nr_p_val or r.get('paleta_id') or '').strip().upper()
        return typ_op in ('PRZESUNIECIE', 'PRZESUNIĘCIE') and ('(podział' in koment or '(podzial' in koment) and (dt_key, p_id_match) in split_signatures

    @classmethod
    def deduplicate_canonical_pass(cls, items: list[dict]) -> list[dict]:
        """Perform second-pass canonical deduplication by transfer order, SSCC, PID, and value."""
        seen_by_order = {}
        seen_by_sscc = {}
        seen_by_pid = {}
        seen_by_val = {}
        final_deduped = []

        for r in items:
            dt_min = r.get('data')
            u_login = str(r.get('user') or '').strip().lower()
            c_typ = MovementClassifier.get_canonical_type(r.get('typ'), r.get('komentarz'))
            nr_p = str(r.get('nr_palety') or '').strip()
            p_id = str(r.get('paleta_id') or '').strip()
            w_val = round(float(r.get('ilosc') or 0.0), 1)

            m_trf_order = re.search(r'Zlecenie\s+przesuni[eę]cia\s+([A-Za-z0-9_\-]+)', str(r.get('komentarz') or ''), re.I)
            order_ref_key = m_trf_order.group(1).strip() if m_trf_order else None
            p_order_ident = nr_p if (nr_p and nr_p != '-') else p_id
            k_order = (order_ref_key, p_order_ident) if (order_ref_key and p_order_ident) else None

            k_sscc = (dt_min, u_login, c_typ, nr_p) if (nr_p and nr_p != '-') else None
            k_pid = (dt_min, u_login, c_typ, p_id) if (p_id and p_id not in ('-', '', 'None', '0')) else None
            k_val = (dt_min, u_login, c_typ, w_val, str(r.get('nazwa') or '').strip().lower()) if w_val > 0 else None

            is_duplicate = False
            existing_match = None

            if k_order and k_order in seen_by_order:
                is_duplicate = True; existing_match = seen_by_order[k_order]
            elif k_sscc and k_sscc in seen_by_sscc:
                is_duplicate = True; existing_match = seen_by_sscc[k_sscc]
            elif k_pid and k_pid in seen_by_pid:
                is_duplicate = True; existing_match = seen_by_pid[k_pid]
            elif k_val and k_val in seen_by_val and c_typ not in ('CREATION', 'DELETION'):
                is_duplicate = True; existing_match = seen_by_val[k_val]

            if is_duplicate and existing_match:
                cls._merge_duplicate_item(existing_match, r, nr_p)
            else:
                if k_order: seen_by_order[k_order] = r
                if k_sscc: seen_by_sscc[k_sscc] = r
                if k_pid: seen_by_pid[k_pid] = r
                if k_val: seen_by_val[k_val] = r
                final_deduped.append(r)

        return final_deduped

    @classmethod
    def _merge_duplicate_item(cls, existing: dict, current: dict, nr_p: str):
        st_curr = str(current.get('stacja') or '')
        st_prev = str(existing.get('stacja') or '')
        if 'LINIA ->' in st_curr or ('->' in st_curr and '->' not in st_prev):
            existing['stacja'] = current['stacja']
            existing['skad'] = current.get('skad', existing.get('skad'))
            existing['dokad'] = current.get('dokad', existing.get('dokad'))
        if (not existing.get('komentarz') or existing['komentarz'] == '-') and current.get('komentarz'):
            existing['komentarz'] = current['komentarz']
        if (not existing.get('nr_palety') or existing['nr_palety'] == '-') and nr_p and nr_p != '-':
            existing['nr_palety'] = nr_p
        if (not existing.get('nazwa') or existing['nazwa'].lower() in ProductValidator.GENERIC_LOCATION_NAMES) and current.get('nazwa') and current['nazwa'].lower() not in ProductValidator.GENERIC_LOCATION_NAMES:
            existing['nazwa'] = current['nazwa']
