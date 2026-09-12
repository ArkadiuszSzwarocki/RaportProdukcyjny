from datetime import datetime

class MovementClassifier:
    """Service responsible for parsing dates and classifying movement categories."""

    @staticmethod
    def parse_dt(r):
        """Safely parse creation datetime from a dictionary row."""
        dt = r.get('created_at')
        if isinstance(dt, datetime):
            return dt
        if isinstance(dt, str):
            try:
                return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        return datetime.min

    @staticmethod
    def get_canonical_type(typ_str: str, comment: str = '') -> str:
        """Normalize various movement type labels into high-level canonical categories for deduplication."""
        t = str(typ_str or '').upper().strip()
        c = str(comment or '').lower()
        if any(k in t for k in ('UTWORZ',)):
            return 'CREATION'
        if any(k in t for k in ('USUN',)):
            return 'DELETION'
        if any(k in t for k in ('PRZYJ', 'PW', 'PZ', 'POTWIERDZ', 'DOSTAWA')):
            return 'RECEPTION'
        if any(k in t for k in ('PODZIA', 'PODZIAL')):
            return 'SPLIT'
        if any(k in t for k in ('WYDA', 'PROD', 'RW', 'POBRANIE')):
            return 'DISPATCH'
        if any(k in t for k in ('PRZESUN', 'TRANSF', 'RELOKAC', 'RUCH', 'MM')):
            if 'podzia' in c or 'podzial' in c:
                return 'SPLIT'
            return 'RELOCATION'
        if any(k in t for k in ('DOSYP',)):
            return 'DOSING'
        if any(k in t for k in ('ZASYP', 'BUFOR')):
            return 'FEED'
        if any(k in t for k in ('CZYSZCZ', 'CLEAN')):
            return 'CLEANING'
        if any(k in t for k in ('INWENT', 'KOREKT')):
            return 'INVENTORY'
        if any(k in t for k in ('OPAKOW', 'TYP')):
            return 'PACKAGING'
        return t

    @classmethod
    def matches_operation_type(cls, item: dict, typ_filter: str) -> bool:
        """Check if an enriched item matches the requested operation type filter."""
        if not typ_filter or typ_filter == 'ALL':
            return True
        t_kw = typ_filter.upper().strip()
        typ_str = (item.get('typ') or '').upper()
        kom_lower = (item.get('komentarz') or '').lower()

        if t_kw in ('UTWORZENIE', 'UTWORZENIE_PALETY', 'UTWORZ'):
            return 'UTWORZ' in typ_str
        if t_kw == 'PRZYJECIE':
            return any(k in typ_str for k in ('PRZYJECIE', 'PRZYJĘCIE', 'PW', 'PZ'))
        if t_kw == 'WYDANIE':
            return any(k in typ_str for k in ('WYDANIE', 'PROD', 'RW', 'WZ'))
        if t_kw == 'PODZIAL':
            return 'PODZIAL' in typ_str or 'podział' in kom_lower or 'podzial' in kom_lower
        if t_kw == 'PRZESUNIECIE':
            return any(k in typ_str for k in ('PRZESUNI', 'TRANSFER', 'RELOKAC', 'RUCH', 'MM')) and 'PODZIAL' not in typ_str
        if t_kw == 'ZASYP':
            return any(k in typ_str for k in ('ZASYP', 'BUFOR'))
        if t_kw == 'DOSYPKA':
            return 'DOSYP' in typ_str
        if t_kw == 'CZYSZCZENIE':
            return any(k in typ_str for k in ('CZYSZCZ', 'CLEAN'))
        if t_kw == 'USUNIECIE':
            return 'USUN' in typ_str
        if t_kw == 'INWENTARYZACJA':
            return any(k in typ_str for k in ('INWENT', 'KOREKT'))
        if t_kw == 'OPAKOWANIE':
            return any(k in typ_str for k in ('OPAKOW', 'TYP'))
        return t_kw in typ_str
