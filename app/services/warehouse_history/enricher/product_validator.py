import re

class ProductValidator:
    """Service responsible for validating and sanitizing product names."""

    GENERIC_NAMES = (
        'surowiec', 'surowiec agro', 'produkt nieznany', 'brak', 'paleta',
        'wyrób gotowy', 'wyrob gotowy', 'wyrób gotowy agro', 'wyrob gotowy agro',
        'wyrób gotowy psd', 'wyrob gotowy psd', 'produkt gotowy', 'wg agro', 'wg psd',
        'bags', 'bag', 'worek', 'karton', 'taśma', 'tasma', 'folia', 'big bag', 'big-bag',
        'opakowanie', 'opakowania', 'workowania', 'workowanie', 'maszyna', 'linia',
        'linia agro', 'linia psd', 'produkcja agro', 'produkcja psd'
    )

    GENERIC_LOCATION_NAMES = (
        '', '-', 'surowiec', 'surowiec agro', 'produkt nieznany', 'brak', 'paleta',
        'wyrób gotowy', 'wyrob gotowy', 'wyrób gotowy agro', 'wyrob gotowy agro',
        'wyrób gotowy psd', 'wyrob gotowy psd', 'produkt gotowy',
        'bags', 'bag', 'worek', 'karton', 'taśma', 'tasma', 'folia', 'big bag', 'big-bag', 'opakowanie', 'opakowania',
        'ms01', 'mp01', 'md01', 'mdm01', 'mop01', 'mgw01', 'mgw02', 'osip', 'bfos', 'oczekujące', 'oczekujace', 'magazyn'
    )

    @classmethod
    def is_invalid_product_name(cls, cand) -> bool:
        """Return True if the candidate name is invalid, empty, or a generic placeholder."""
        if not cand:
            return True
        c_clean = str(cand).strip()
        c_lower = c_clean.lower()
        if not c_clean or c_clean in ('-', 'None', 'null', 'brak', 'none'):
            return True
        if c_lower in cls.GENERIC_NAMES:
            return True
        if c_clean.isdigit():
            return True
        if re.search(r'^\d+(\.\d+)?\s*(kg|szt)', c_clean, re.IGNORECASE):
            return True
        # Reject plan/order/location tokens in product names
        if any(term in c_lower for term in ('plan #', 'zlecenie #', 'lok:', '(lok', 'regał', 'regal', 'bufor', 'status:')):
            return True
        if ')' in c_clean or c_clean.startswith('('):
            return True
        # Document numbers: wz26, WZ-26, WZ/123, FV123, faktura 12, etc.
        if re.match(r'^(wz[\s\-_/0-9].*|wz\d+|fv[\s\-_/0-9].*|fv\d+|faktura[\s\-_/0-9].*|dok[\s\-_/0-9].*)$', c_lower):
            return True
        # Locations: MS01, MP01, OSIP, BFOS, MGW01, R060502, etc.
        if re.match(r'^(R\d+|MS\d+|MP\d+|MD\d+|MDM\d+|MOP\d+|MGW\d+|OSIP|BFOS|BF_\w+|A\d+|OS\d+|RAMPA|MIX\d*|BB\d+|MZ\d+|ZB\d+|KO\d+|WZ\d+|OCZEKUJ[AĄ]CE|MAGAZYN)$', c_clean, re.IGNORECASE):
            return True
        return False
