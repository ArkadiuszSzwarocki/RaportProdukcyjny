"""Configuration and helper functions for warehouse deliveries module."""
from datetime import datetime

# Domyślne lokalizacje magazynowe RaportProdukcyjny
LOKALIZACJE_ZRODLO = [
    'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
    'OSIP', 'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'KO01', 'PSD', 'PSD01',
    'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
]

# Regały R04 (18 poz.: 6 kolumn x 3 poziomy), R05 (20 poz.), R06 (10 poz.), R07 (44 poz.: 11 kolumn x 4 poziomy)
_r04 = [f'R04{str(c).zfill(2)}{str(l).zfill(2)}' for l in range(1, 4) for c in range(1, 7)]
_r05 = [f'R05{str(i+1).zfill(2)}01' for i in range(20)]
_r06 = [f'R06{str(i+1).zfill(2)}01' for i in range(10)]
_r07 = sorted([f'R07{str(c).zfill(2)}{str(l).zfill(2)}' for c in range(1, 12) for l in range(1, 5)])
# OSIP – lokalizacje A01..A99 oraz BFOS (+ wsparcie legacy OS01..OS77)
_osip = [f'A{str(i+1).zfill(2)}' for i in range(99)] + ['BFOS'] + [f'OS{str(i+1).zfill(2)}' for i in range(77)]
# Stanowiska produkcyjne BB (BB01-BB06, BB11-BB22), MZ (MZ07-MZ10, MZ23-MZ24)
_bb = [f'BB{str(i).zfill(2)}' for i in range(1, 25) if i not in (7, 8, 9, 10, 23, 24)]
_mz = ['MZ07', 'MZ08', 'MZ09', 'MZ10', 'MZ23', 'MZ24']
_ko = [f'KO{str(i+1).zfill(2)}' for i in range(22)]

LOKALIZACJE_SZCZEGOLOWE = {
    'Magazyny': LOKALIZACJE_ZRODLO,
    'Regał R04': _r04,
    'Regał R05': _r05,
    'Regał R06': _r06,
    'Regał R07': _r07,
    'OSIP (A01-A99, BFOS)': _osip,
    'Stanowiska BB': _bb,
    'Stanowiska MZ': _mz,
    'Stanowiska KO': _ko,
}

# Płaska lista na potrzeby selecta źródło/cel
LOKALIZACJE = sorted(list(set(LOKALIZACJE_ZRODLO + _ko + ['R04', 'R05', 'R06', 'R07', 'PSD01', 'BFOS'])))
LOKALIZACJE_CEL = ['BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'MS01', 'MP01', 'PSD01']
BUFORY = ['BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS']


def _safe_float(value):
    try:
        if value in (None, ''):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_datetime_str(value):
    if not value:
        return '-'
    if isinstance(value, str):
        return value
    try:
        return value.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(value)


def _format_label_weight(value):
    qty = _safe_float(value)
    if abs(qty - round(qty)) < 1e-6:
        return str(int(round(qty)))
    return f"{qty:.2f}".rstrip('0').rstrip('.')
