# cspell:words sscc
"""
Serwis obsługi wydań zewnętrznych na samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Logika biznesowa walidacji i wykonywania wyjazdów ciężarówek/pojazdów dostawczych.
"""

from app.repositories.warehouse_dispatch_repository import WarehouseDispatchRepository
from app.services.scanner_service import ScannerService
from app.dto.service_result import ServiceResult



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

        if row.get('duplicate_sscc'):
            # Keep the invariant visible to the API caller instead of loading
            # an arbitrary pallet from one of the warehouse tables.
            return row

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
        """Validate server-owned pallets and commit the entire loading together."""
        import math
        from flask import has_request_context
        from app.core.production_permissions import _page_allowed
        from app.services.lab_quality_service import LabQualityService
        if not isinstance(payload, dict):
            return False, 'Wymagane dane załadunku.'
        items = payload.get('pallets', [payload])
        if not isinstance(items, list) or not items or len(items) > 1000:
            return False, 'Nieprawidłowa lista palet.'
        expected = payload.get('expected_count', payload.get('oczekiwana_ilosc_palet'))
        if expected is not None:
            try:
                if int(expected) != len(items) or int(expected) <= 0:
                    return False, 'Blokada wysyłki: Niekompletny załadunek.'
            except (ValueError, TypeError):
                return False, 'Nieprawidłowa oczekiwana liczba palet.'
        required_batch = str(payload.get('required_batch') or payload.get('wymagana_partia') or '').strip().upper()
        entries, seen = [], set()
        try:
            for item in items:
                if not isinstance(item, dict):
                    return False, 'Nieprawidłowe dane palety.'
                code = str(item.get('nr_palety') or item.get('displayId') or '').strip()
                if not code:
                    return False, 'Wymagany jest numer palety do załadunku.'
                pallet = self.lookup_pallet_for_dispatch(code, preferred_line=payload.get('linia') or 'AGRO')
                if not pallet or pallet.get('duplicate_sscc'):
                    return False, 'Nie znaleziono jednoznacznej aktywnej palety.'
                key = (pallet['src_table'], pallet['id'])
                if key in seen:
                    return False, 'Ta sama paleta występuje wielokrotnie w załadunku.'
                seen.add(key)
                if has_request_context() and not _page_allowed(str(pallet['linia']).upper(), 'magazyn', write=True):
                    return False, 'Brak uprawnień do magazynu tej palety.'
                quantity = float(item.get('ilosc_kg', item.get('amount', 0)))
                if not math.isfinite(quantity) or quantity <= 0 or quantity > pallet['amount']:
                    return False, 'Nieprawidłowa ilość lub niewystarczający stan palety.'
                if required_batch and str(pallet.get('batch') or '').upper() != required_batch:
                    return False, 'Blokada wysyłki: Niezgodność partii.'
                quality = LabQualityService.check_pallet_lab_status(pallet['nr_palety'])
                if quality.get('is_blocked'):
                    return False, 'Blokada wysyłki: ' + str(quality.get('message') or 'Blokada LAB.')
                entries.append({
                    'pallet_id': pallet['id'], 'src_table': pallet['src_table'],
                    'nr_palety': pallet['nr_palety'], 'nazwa_produktu': pallet['nazwa_produktu'],
                    'typ_palety': pallet['type'], 'linia': pallet['linia'], 'ilosc_kg': quantity,
                    'batch': pallet.get('batch'), 'required_batch': required_batch,
                    'magazynier': magazynier_login,
                    **{field: str(payload.get(field) or '').strip() or None for field in
                       ('nr_rejestracyjny', 'kierowca', 'odbiorca', 'nr_dokumentu_wz', 'uwagi')}
                })
            ids = self._repository.dispatch_batch(entries)
            if not ids or len(ids) != len(entries):
                return False, 'Nie zapisano pełnego załadunku.'
            if len(ids) == 1:
                return True, f'Załadunek został zarejestrowany (ID #{ids[0]}).'
            return True, f'Zarejestrowano załadunek {len(ids)} palet na samochód.'
        except (ValueError, TypeError, KeyError):
            return False, 'Nieprawidłowe dane lub zmieniony stan palety. Zeskanuj ponownie.'
        except Exception:
            return False, 'Nie zapisano załadunku. Sprawdź stan magazynu i spróbuj ponownie.'
