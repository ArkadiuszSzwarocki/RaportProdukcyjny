import re
from app.services.warehouse_history.enricher.movement_classifier import MovementClassifier

class LocationRouteResolver:
    """Service responsible for reconstructing physical warehouse routing and location chains."""

    INVALID_LOC_WORDS = {
        'workowania', 'workowanie', 'linii', 'linia', 'lok', 'lokalizacji', 'lokalizacja',
        'dostawy', 'dostawa', 'produkcji', 'produkcja', 'stacji', 'stacja', 'maszyny', 'maszyna',
        'systemu', 'system', 'palety', 'paleta', 'palet', 'auta', 'auto', 'naczepy', 'naczepa',
        'rampy', 'rampa', 'magazynu', 'magazyn', 'bufora', 'bufor', 'regału', 'regal', 'nowej',
        'podziału', 'podzialu', 'odjęcia', 'odjecia', 'stanie', 'stan', 'status', 'zlecenia', 'zlecenie', 'plan'
    }

    @classmethod
    def extract_locations_from_comment(cls, koment: str, src_loc: str, dst_loc: str) -> tuple[str, str]:
        """Extract source and destination locations from movement comment."""
        m_from_to = re.search(r'(?:(?:przesunięcie|przeniesienie|przeniesiono|przesunięto|transfer|wydano|ruch)\s+(?:skanerem:\s*)?)?(?:z|ze)\s+(?:regału\s+)?([A-Za-z0-9\-_]+)\s+(?:do|na|w)\s+(?:regał\s+|regału\s+)?([A-Za-z0-9\-_]+)', koment, re.IGNORECASE)
        if m_from_to:
            c_src = m_from_to.group(1).strip()
            c_dst = m_from_to.group(2).strip()
            if c_src.lower() not in ('none', 'null', 'brak', '-', '') and c_src.lower() not in cls.INVALID_LOC_WORDS:
                src_loc = c_src
            if c_dst.lower() not in ('none', 'null', 'brak', '-', '') and c_dst.lower() not in cls.INVALID_LOC_WORDS:
                dst_loc = c_dst

        if not src_loc or not dst_loc or src_loc == dst_loc:
            m_scanner = re.search(r'(?:przesunięcie\s+skanerem:\s*)([A-Za-z0-9\-_]+)\s*->\s*([A-Za-z0-9\-_]+)', koment, re.IGNORECASE)
            if m_scanner:
                c_src = m_scanner.group(1).strip()
                c_dst = m_scanner.group(2).strip()
                if c_src.lower() not in ('none', 'null', 'brak', '-', '') and c_src.lower() not in cls.INVALID_LOC_WORDS:
                    src_loc = c_src
                if c_dst.lower() not in ('none', 'null', 'brak', '-', '') and c_dst.lower() not in cls.INVALID_LOC_WORDS:
                    dst_loc = c_dst

        if not dst_loc:
            m_disp = re.search(r'wydanie\s+do\s+przesunięcia:\s*.*?->\s*([A-Za-z0-9\-_]+)', koment, re.IGNORECASE)
            if m_disp and m_disp.group(1).lower() not in cls.INVALID_LOC_WORDS:
                dst_loc = m_disp.group(1).strip()
                if not src_loc:
                    src_loc = 'Magazyn'

        if not dst_loc or not src_loc:
            m_lp = re.search(r'wydanie.*?na\s+(?:maszynę|maszyne|stację|stacje)\s+([A-Za-z0-9\-_]+)\s+z\s+([A-Za-z0-9\-_]+)', koment, re.IGNORECASE)
            if m_lp:
                if m_lp.group(1).lower() not in cls.INVALID_LOC_WORDS:
                    dst_loc = m_lp.group(1).strip()
                if m_lp.group(2).lower() not in cls.INVALID_LOC_WORDS:
                    src_loc = m_lp.group(2).strip()

        if not dst_loc:
            m_dest = re.search(r'(?:przeniesiono\s+na|przyjęcie.*?na|na\s+regał|do\s+stacji)\s+([A-Za-z0-9\-_]{2,15})', koment, re.IGNORECASE)
            if m_dest and m_dest.group(1).lower() not in cls.INVALID_LOC_WORDS:
                dst_loc = m_dest.group(1).strip()

        if not dst_loc:
            m_st_kw = re.search(r'(?:do\s+stacji|na\s+stację|na\s+stacje|stacja|stacji|zasyp\s+(?:na\s+)?)\s*([A-Za-z0-9\-_]{2,10})', koment, re.IGNORECASE)
            if m_st_kw and m_st_kw.group(1).lower() not in cls.INVALID_LOC_WORDS:
                dst_loc = m_st_kw.group(1).strip().upper()

        if not dst_loc:
            m_st_code = re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)\b', koment, re.IGNORECASE)
            if m_st_code:
                dst_loc = m_st_code.group(1).strip().upper()

        if not src_loc:
            m_src_explicit = re.search(r'(?:z\s+lok(?:alizacji)?[:\s]+|z\s+regału[:\s]+|z\s+bufora[:\s]+|\(lok[:\s]+)([A-Za-z0-9\-_]{2,15})', koment, re.IGNORECASE)
            if m_src_explicit and m_src_explicit.group(1).lower() not in cls.INVALID_LOC_WORDS:
                src_loc = m_src_explicit.group(1).strip().replace(')', '').upper()

        if not src_loc:
            m_src_kw = re.search(r'(?:z|ze)\s+(?:regału\s+|bufora\s+|magazynu\s+)?([A-Za-z0-9\-_]{2,15})\b', koment, re.IGNORECASE)
            if m_src_kw and m_src_kw.group(1).lower() not in cls.INVALID_LOC_WORDS:
                src_loc = m_src_kw.group(1).strip()

        if not src_loc or not dst_loc or src_loc == dst_loc:
            m_arrow = re.search(r'\b([A-Za-z0-9\-_]{2,15})\s*->\s*([A-Za-z0-9\-_]{2,15})\b', koment)
            if m_arrow:
                c_src = m_arrow.group(1).strip()
                c_dst = m_arrow.group(2).strip()
                if c_src.lower() not in ('none', 'null', 'brak', '-', '') and c_src.lower() not in cls.INVALID_LOC_WORDS:
                    src_loc = c_src
                if c_dst.lower() not in ('none', 'null', 'brak', '-', '') and c_dst.lower() not in cls.INVALID_LOC_WORDS:
                    dst_loc = c_dst

        return src_loc, dst_loc

    @classmethod
    def resolve_routes_chronological(cls, all_rows: list[dict]) -> dict:
        """Process rows chronologically to determine source, destination, and stacja routing."""
        all_rows_chrono = sorted(all_rows, key=MovementClassifier.parse_dt)
        pallet_loc_tracker = {}

        for r in all_rows_chrono:
            koment = str(r.get('komentarz') or '').strip()
            src_loc = str(r.get('lokalizacja_zrodlowa') or '').strip()
            dst_loc = str(r.get('lokalizacja_docelowa') or '').strip()
            typ_op = str(r.get('typ_ruchu') or '').upper()

            if src_loc.lower() in ('none', 'null', 'brak', '-', '') or src_loc.lower() in cls.INVALID_LOC_WORDS:
                src_loc = ''
            if dst_loc.lower() in ('none', 'null', 'brak', '-', '') or dst_loc.lower() in cls.INVALID_LOC_WORDS:
                dst_loc = ''

            is_pkg_change = (
                typ_op in ('ZMIANA_OPAKOWANIA', 'OPAKOWANIE', 'ZMIANA_TYPU_MATERIALU', 'ZMIANA_TYPU_MATERIALU_BULK')
                or 'opakowan' in koment.lower()
                or 'zmiana opakowania' in koment.lower()
                or 'zmiana typu materia' in koment.lower()
            )

            if koment and not is_pkg_change:
                src_loc, dst_loc = cls.extract_locations_from_comment(koment, src_loc, dst_loc)

            p_key = r.get('nr_palety') or (f"{r.get('linia_ruch')}_{r.get('paleta_id')}" if r.get('paleta_id') else None)
            prev_pallet_loc = pallet_loc_tracker.get(p_key) if p_key else None

            is_split_creation = any(k in typ_op for k in ('PODZIAL_PALETY', 'PODZIAL_UTWORZENIE')) or (typ_op == 'PODZIAL' and 'utworzono z podziału' in koment.lower())
            is_split_deduction = any(k in typ_op for k in ('PODZIAL_ODJECIE',)) or (typ_op == 'PODZIAL' and ('odjęto' in koment.lower() or 'odjeto' in koment.lower()))
            is_pallet_creation = any(k in typ_op for k in ('UTWORZENIE', 'UTWORZENIE_PALETY', 'UTWORZ')) or 'utworzono palet' in koment.lower()
            is_pallet_deletion = any(k in typ_op for k in ('USUN', 'USUNIECIE', 'USUNIĘCIE')) or 'usunięto palet' in koment.lower() or 'usunieto palet' in koment.lower()
            is_machine_roll = any(k in typ_op for k in ('POBRANIE_NA_MASZYNE', 'POBRANIE_DO_PRODUKCJI')) or any(k in koment.lower() for k in ('wsadzenie rolki', 'dobrana rolka', 'pobranie folii'))

            if is_split_creation:
                m_mother = re.search(r'palety\s+(?:matki\s+)?(SUR\d{6,20}|AGR\d{6,20}|PSD\d{6,20}|\d{18,20})', koment, re.IGNORECASE)
                mother_code = m_mother.group(1).strip() if m_mother else ''
                mother_label = f"Matka: {mother_code}" if mother_code else "Paleta matka"
                dst_loc = dst_loc or (r.get('lokalizacja_docelowa') if r.get('lokalizacja_docelowa') and r.get('lokalizacja_docelowa') != '-' else '') or prev_pallet_loc or 'MS01'
                src_loc = mother_label
                stacja_val = f"{src_loc} -> {dst_loc}"

            elif is_split_deduction:
                m_child = re.search(r'(?:do\s+nowej\s+palety|nowa\s+paleta:)\s*(SUR\d{6,20}|AGR\d{6,20}|PSD\d{6,20}|\d{18,20})', koment, re.IGNORECASE)
                child_code = m_child.group(1).strip() if m_child else ''
                child_label = f"Potomna: {child_code}" if child_code else "Nowa paleta"

                m_mother_loc = re.search(r'(?:na|w)\s+([A-Za-z0-9\-_]{2,10})\b', koment)
                extracted_m_loc = m_mother_loc.group(1).strip() if m_mother_loc and m_mother_loc.group(1).lower() not in cls.INVALID_LOC_WORDS else ''
                src_loc = extracted_m_loc or src_loc or (r.get('lokalizacja_zrodlowa') if r.get('lokalizacja_zrodlowa') and r.get('lokalizacja_zrodlowa') != '-' else '') or prev_pallet_loc or 'Magazyn'
                dst_loc = child_label
                stacja_val = f"{src_loc} -> {dst_loc}"

            elif is_pkg_change:
                cur_loc = dst_loc or src_loc or (r.get('lokalizacja_docelowa') if r.get('lokalizacja_docelowa') and r.get('lokalizacja_docelowa') != '-' else '') or prev_pallet_loc or 'OCZEKUJĄCE'
                src_loc = cur_loc
                dst_loc = cur_loc
                stacja_val = cur_loc

            elif is_pallet_creation:
                line_nm = 'AGRO' if (r.get('linia_ruch') or r.get('linia') or '').upper() == 'AGRO' else 'PSD'
                src_loc = f"Linia {line_nm}"
                dst_loc = 'OCZEKUJĄCE'
                stacja_val = f"{src_loc} -> {dst_loc}"

            elif is_pallet_deletion:
                src_loc = prev_pallet_loc if (prev_pallet_loc and prev_pallet_loc.lower() not in cls.INVALID_LOC_WORDS) else 'OCZEKUJĄCE'
                dst_loc = 'USUNIĘCIE'
                stacja_val = f"{src_loc} -> {dst_loc}"

            elif is_machine_roll:
                m_lok = re.search(r'(?:lok(?:alizacji)?[:\s]+|regału[:\s]+|\(lok[:\s]+)([A-Za-z0-9\-_]+)', koment, re.IGNORECASE)
                if m_lok and m_lok.group(1).lower() not in cls.INVALID_LOC_WORDS:
                    src_loc = m_lok.group(1).strip().replace(')', '').upper()
                if not src_loc or src_loc.lower() in cls.INVALID_LOC_WORDS:
                    src_loc = prev_pallet_loc if (prev_pallet_loc and prev_pallet_loc.lower() not in cls.INVALID_LOC_WORDS) else 'MP01'
                dst_loc = 'Maszyna'
                stacja_val = f"{src_loc} -> {dst_loc}"

            else:
                is_relocation = any(term in typ_op for term in ('PRZESUNIECIE', 'PRZESUNIĘCIE', 'TRANSFER', 'RELOKACJA', 'RUCH', 'WYDANIE_PRZESUNIECIE'))
                is_station_target = bool(re.search(r'^(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)$', dst_loc, re.IGNORECASE))
                is_station_kw = any(k in typ_op for k in ('WYDANIE_PRODUKCJA', 'PRODUKCJA', 'ZASYP', 'DOSYPKA', 'WYDANIE_STACJA', 'ZASYP_STACJA', 'STACJA', 'POBRANIE')) or any(k in koment.lower() for k in ('do stacji', 'na stację', 'na stacje', 'zasyp', 'dosypka', 'wydano na stację', 'wydanie na produkcję', 'wydanie do produkcji'))
                is_station_issue = is_station_target or (is_station_kw and bool(re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)\b', koment, re.IGNORECASE)))
                is_reception = any(k in typ_op for k in ('PRZYJECIE', 'PRZYJĘCIE', 'DOSTAWA', 'PW', 'PZ')) or any(k in koment.lower() for k in ('przyjęcie z dostawy', 'przyjecie z dostawy', 'dostawa zewnętrzna', 'dostawa zewnetrzna', 'z dostawy', 'dostawa'))
                is_osip = dst_loc.upper() in ('OSIP', 'BFOS') or bool(re.match(r'^(OS\d+|A\d+)$', dst_loc, re.IGNORECASE)) or (r.get('linia_ruch') or r.get('linia') or '').upper() == 'OSIP' or 'osip' in koment.lower()

                if is_station_issue:
                    if not is_station_target:
                        m_st = re.search(r'\b(BB\d+|MZ\d+|WZ\d+|KO\d+|ZB\d+|MIX\d*)\b', koment, re.IGNORECASE)
                        if m_st:
                            dst_loc = m_st.group(1).upper()
                    if not src_loc or src_loc in ('-', 'Magazyn') or src_loc == dst_loc:
                        if prev_pallet_loc and prev_pallet_loc != dst_loc:
                            src_loc = prev_pallet_loc
                        else:
                            line_code = (r.get('linia_ruch') or r.get('linia') or 'PSD').upper()
                            src_loc = 'MS01' if line_code == 'AGRO' else ('OSIP' if line_code == 'OSIP' else 'MP01')
                    stacja_val = f"{src_loc} -> {dst_loc}"

                elif is_reception:
                    is_acceptance_from_pending = ('przyjęcie z dostawy' in koment.lower() or 'przyjecie z dostawy' in koment.lower() or prev_pallet_loc in ('OCZEKUJĄCE', 'OCZEKUJACE') or src_loc in ('OCZEKUJĄCE', 'OCZEKUJACE')) and (dst_loc not in ('OCZEKUJĄCE', 'OCZEKUJACE'))
                    is_initial_delivery = dst_loc in ('OCZEKUJĄCE', 'OCZEKUJACE') or any(k in koment.lower() for k in ('przyjęcie zewnętrzne', 'przyjecie zewnetrzne', 'dostawa zewnętrzna', 'dostawa zewnetrzna')) or typ_op in ('DOSTAWA', 'PZ')

                    if is_acceptance_from_pending:
                        src_loc = 'OCZEKUJĄCE'
                        dst_loc = dst_loc if (dst_loc and dst_loc not in ('-', 'None', 'null', 'brak')) else ('OSIP' if is_osip else 'MS01')
                        stacja_val = f"{src_loc} -> {dst_loc}"
                    elif is_initial_delivery:
                        src_loc = 'DOSTAWA'
                        dst_loc = 'OCZEKUJĄCE'
                        stacja_val = f"{src_loc} -> {dst_loc}"
                    elif is_osip:
                        dst_loc = dst_loc or 'OSIP'
                        if any(k in koment.lower() for k in ('transfer', 'z centrali', 'z ms01')):
                            src_loc = src_loc if (src_loc and src_loc not in ('-', 'None', 'null', 'brak', 'OCZEKUJACE', 'OCZEKUJĄCE')) else 'CENTRALA'
                        elif prev_pallet_loc and prev_pallet_loc != dst_loc:
                            src_loc = prev_pallet_loc
                        else:
                            src_loc = 'OCZEKUJĄCE' if any(k in koment.lower() for k in ('przyjęcie', 'przyjecie', 'dostaw')) else 'DOSTAWA'
                        stacja_val = f"{src_loc} -> {dst_loc}"
                    else:
                        src_loc = src_loc if (src_loc and src_loc not in ('-', 'None', 'null', 'brak')) else (prev_pallet_loc or 'DOSTAWA')
                        dst_loc = dst_loc or 'OCZEKUJĄCE'
                        stacja_val = dst_loc if src_loc == dst_loc else f"{src_loc} -> {dst_loc}"

                elif is_relocation:
                    if not src_loc or src_loc == dst_loc:
                        src_loc = prev_pallet_loc if (prev_pallet_loc and prev_pallet_loc != dst_loc) else 'Magazyn'
                    if not dst_loc:
                        dst_loc = prev_pallet_loc if (prev_pallet_loc and prev_pallet_loc != src_loc) else 'Magazyn'
                    if src_loc == dst_loc and src_loc == 'Magazyn':
                        stacja_val = 'Magazyn'
                    elif src_loc == dst_loc:
                        stacja_val = f"Magazyn -> {dst_loc}"
                    else:
                        stacja_val = f"{src_loc} -> {dst_loc}"
                elif src_loc and dst_loc and src_loc != dst_loc:
                    stacja_val = f"{src_loc} -> {dst_loc}"
                else:
                    stacja_val = dst_loc or src_loc or '-'

            if p_key and dst_loc and dst_loc not in ('-', 'Magazyn') and not is_pkg_change:
                pallet_loc_tracker[p_key] = dst_loc
            elif p_key and src_loc and src_loc not in ('-', 'Magazyn') and p_key not in pallet_loc_tracker and not is_pkg_change:
                pallet_loc_tracker[p_key] = src_loc

            r['_stacja_val'] = stacja_val
            r['_src_loc'] = src_loc
            r['_dst_loc'] = dst_loc

        return pallet_loc_tracker
