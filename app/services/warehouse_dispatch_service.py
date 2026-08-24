"""
Serwis obsługi wydań zewnętrznych na samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Logika biznesowa walidacji i wykonywania wyjazdów ciężarówek/pojazdów dostawczych.
"""

from app.repositories.warehouse_dispatch_repository import WarehouseDispatchRepository
from app.services.scanner_service import ScannerService


class WarehouseDispatchService:
    """Serwis obsługi załadunków samochodowych."""

    def __init__(self, repository=None):
        self._repository = repository or WarehouseDispatchRepository()

    def lookup_pallet_for_dispatch(self, code: str, preferred_line: str = 'AGRO') -> dict | None:
        """Wyszukuje aktywną paletę do załadunku na podstawie zeskanowanego kodu.

        Args:
            code (str): Kod kreskowy, SSCC lub ID palety.
            preferred_line (str): Preferowana linia ('AGRO' lub 'PSD').

        Returns:
            dict | None: Znormalizowane dane palety do załadunku.
        """
        if not code or not str(code).strip():
            return None

        normalized = ScannerService._normalize_scanned_code(code)
        if not normalized:
            normalized = str(code).strip().upper()

        prefix, item_id = ScannerService._extract_prefixed_id(normalized)
        
        row = self._repository.find_pallet_by_code(
            code=normalized,
            preferred_line=preferred_line,
            prefix=prefix,
            item_id=item_id
        )
        if not row:
            return None

        display_id = row.get('nr_palety')
        if not display_id:
            typ_prefix = 'SUR' if row.get('typ') == 'Surowiec' else ('OPK' if row.get('typ') == 'Opakowanie' else 'PAL')
            display_id = f"{typ_prefix}-{row.get('id')}"

        return {
            'id': row.get('id'),
            'pallet_id': row.get('id'),
            'nr_palety': row.get('nr_palety') or display_id,
            'displayId': display_id,
            'productName': row.get('nazwa', ''),
            'nazwa_produktu': row.get('nazwa', ''),
            'amount': float(row.get('stan_magazynowy') or 0.0),
            'ilosc_kg': float(row.get('stan_magazynowy') or 0.0),
            'location': row.get('lokalizacja') or '-',
            'batch': row.get('nr_partii') or '-',
            'type': row.get('typ', 'Surowiec'),
            'linia': row.get('linia', preferred_line),
            'src_table': row.get('src_table')
        }

    def get_dispatches_history(self, limit=50, linia=None):
        """Pobiera historię wydań zewnętrznych na samochód.

        Args:
            limit (int): Maksymalna liczba rekordów.
            linia (str, optional): Linia/oddział np. 'OSIP', 'AGRO', 'PSD'.

        Returns:
            list[dict]: Lista zrealizowanych załadunków.
        """
        dispatches = self._repository.get_recent_dispatches(limit=limit, linia=linia)
        results = []
        for item in dispatches:
            if isinstance(item, dict):
                item_dict = dict(item)
                if item_dict.get('created_at'):
                    try:
                        item_dict['created_at'] = item_dict['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        item_dict['created_at'] = str(item_dict['created_at'])
                results.append(item_dict)
            elif isinstance(item, (tuple, list)):
                created = item[11] if len(item) > 11 else None
                if created:
                    try:
                        created = created.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        created = str(created)
                results.append({
                    'id': item[0] if len(item) > 0 else None,
                    'nr_palety': item[1] if len(item) > 1 else '',
                    'nazwa_produktu': item[2] if len(item) > 2 else '',
                    'typ_palety': item[3] if len(item) > 3 else 'Surowiec',
                    'ilosc_kg': float(item[4] or 0.0) if len(item) > 4 else 0.0,
                    'nr_rejestracyjny': item[5] if len(item) > 5 else '',
                    'kierowca': item[6] if len(item) > 6 else '',
                    'odbiorca': item[7] if len(item) > 7 else '',
                    'nr_dokumentu_wz': item[8] if len(item) > 8 else '',
                    'uwagi': item[9] if len(item) > 9 else '',
                    'magazynier': item[10] if len(item) > 10 else '',
                    'created_at': created
                })
        return results

    def group_dispatches_by_wz(self, dispatches):
        """Grupuje płaską listę wydań zewnętrznych według numeru dokumentu WZ lub numeru rejestracyjnego."""
        if not dispatches:
            return []

        groups_map = {}
        for d in dispatches:
            wz = (d.get('nr_dokumentu_wz') or '').strip()
            reg = (d.get('nr_rejestracyjny') or '').strip()
            
            if wz:
                group_key = f"WZ:{wz.upper()}"
            elif reg:
                group_key = f"REG:{reg.upper()}"
            else:
                group_key = f"DISPATCH:{d.get('id')}"

            if group_key not in groups_map:
                groups_map[group_key] = {
                    'group_key': group_key,
                    'nr_dokumentu_wz': wz or (f"Brak WZ ({reg})" if reg else f"Wyjazd #{d.get('id')}"),
                    'has_wz': bool(wz),
                    'nr_rejestracyjny': reg or 'Brak nr rej.',
                    'kierowca': d.get('kierowca') or 'Brak danych',
                    'odbiorca': d.get('odbiorca') or 'Brak danych',
                    'magazynier': d.get('magazynier') or 'Brak',
                    'created_at': d.get('created_at') or '-',
                    'items': [],
                    'pozycje': [],
                    'pallets_count': 0,
                    'total_weight_kg': 0.0
                }

            group = groups_map[group_key]
            group['items'].append(d)
            group['pozycje'].append(d)
            group['pallets_count'] += 1
            group['total_weight_kg'] += float(d.get('ilosc_kg') or 0.0)
            if d.get('created_at') and (not group['created_at'] or group['created_at'] == '-'):
                group['created_at'] = d.get('created_at')

        return list(groups_map.values())

    def dispatch_pallet_to_vehicle(self, payload, magazynier_login):
        """Wykonuje wydanie zewnętrzne jednej lub wielu palet na samochód.

        Args:
            payload (dict): Dane załadunku (pallets lub pojedyncza paleta + dane transportowe).
            magazynier_login (str): Login magazyniera.

        Returns:
            tuple[bool, str]: (sukces, komunikat).
        """
        pallets = payload.get('pallets')
        nr_rejestracyjny = payload.get('nr_rejestracyjny', '').strip() or None
        kierowca = payload.get('kierowca', '').strip() or None
        odbiorca = payload.get('odbiorca', '').strip() or None
        nr_dokumentu_wz = payload.get('nr_dokumentu_wz', '').strip() or None
        uwagi = payload.get('uwagi', '').strip() or None
        linia = payload.get('linia', 'AGRO')

        # Jeśli przekazano listę wielu palet do zbiorczego załadunku
        if isinstance(pallets, list) and len(pallets) > 0:
            dispatched_count = 0
            total_kg = 0.0
            for p in pallets:
                nr_palety = str(p.get('nr_palety') or p.get('displayId') or '').strip()
                nazwa_produktu = str(p.get('nazwa_produktu') or p.get('productName') or '').strip()
                if not nr_palety or not nazwa_produktu:
                    continue

                ilosc_kg = float(p.get('ilosc_kg') or p.get('amount') or 0.0)
                typ_palety = p.get('typ_palety') or p.get('type') or 'Surowiec'
                pallet_id = p.get('pallet_id') or p.get('id')
                p_linia = p.get('linia') or linia
                src_table = p.get('src_table')

                if pallet_id and ilosc_kg > 0:
                    try:
                        self._repository.deduct_pallet_stock(
                            pallet_id=int(pallet_id),
                            typ_palety=typ_palety,
                            linia=p_linia,
                            ilosc_kg=ilosc_kg,
                            src_table=src_table
                        )
                    except Exception:
                        pass

                data = {
                    'nr_palety': nr_palety,
                    'nazwa_produktu': nazwa_produktu,
                    'typ_palety': typ_palety,
                    'ilosc_kg': ilosc_kg,
                    'nr_rejestracyjny': nr_rejestracyjny,
                    'kierowca': kierowca,
                    'odbiorca': odbiorca,
                    'nr_dokumentu_wz': nr_dokumentu_wz,
                    'uwagi': uwagi,
                    'magazynier': magazynier_login,
                    'linia': p_linia
                }
                did = self._repository.create_dispatch(data)
                if did:
                    dispatched_count += 1
                    total_kg += ilosc_kg

            if dispatched_count > 0:
                return True, f"Zarejestrowano załadunek {dispatched_count} palet na samochód (łączna waga: {total_kg:.2f} kg)."
            return False, "Nie udało się zapisać palet z listy załadunku."

        # Pojedyncza paleta (kompatybilność wsteczna)
        nr_palety = payload.get('nr_palety')
        nazwa_produktu = payload.get('nazwa_produktu')

        if not nr_palety or not str(nr_palety).strip():
            return False, "Wymagany jest numer palety do załadunku."

        if not nazwa_produktu or not str(nazwa_produktu).strip():
            return False, "Wymagana jest nazwa produktu."

        ilosc_kg = float(payload.get('ilosc_kg', 0.0) or 0.0)
        typ_palety = payload.get('typ_palety', 'Surowiec')
        pallet_id = payload.get('pallet_id')

        data = {
            'nr_palety': str(nr_palety).strip(),
            'nazwa_produktu': str(nazwa_produktu).strip(),
            'typ_palety': typ_palety,
            'ilosc_kg': ilosc_kg,
            'nr_rejestracyjny': nr_rejestracyjny,
            'kierowca': kierowca,
            'odbiorca': odbiorca,
            'nr_dokumentu_wz': nr_dokumentu_wz,
            'uwagi': uwagi,
            'magazynier': magazynier_login,
            'linia': linia
        }

        # Opcjonalne odliczenie stanu z tabeli źródłowej magazynu
        if pallet_id and ilosc_kg > 0:
            try:
                self._repository.deduct_pallet_stock(
                    pallet_id=int(pallet_id),
                    typ_palety=typ_palety,
                    linia=linia,
                    ilosc_kg=ilosc_kg,
                    src_table=payload.get('src_table')
                )
            except Exception:
                pass

        dispatch_id = self._repository.create_dispatch(data)
        if dispatch_id:
            return True, f"Załadunek na samochód palety {nr_palety} został zarejestrowany (ID #{dispatch_id})."
        return False, "Błąd podczas rejestracji załadunku na samochód."
