"""Configuration and helper functions for warehouse deliveries module."""
from datetime import datetime

# Lokalizacje z systemu Mleczna Droga
LOKALIZACJE_ZRODLO = [
    'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
    'OSIP', 'BF_MS01', 'BF_MP01', 'KO01', 'PSD', 'PSD01',
    'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
]

# Regały R04 (20 poz.), R05 (20 poz.), R06 (10 poz.), R07 (20 poz.)
_r04 = [f'R04{str(i+1).zfill(2)}01' for i in range(20)]
_r05 = [f'R05{str(i+1).zfill(2)}01' for i in range(20)]
_r06 = [f'R06{str(i+1).zfill(2)}01' for i in range(10)]
_r07 = [f'R07{str(i+1).zfill(2)}01' for i in range(20)]
# OSIP – 77 lokalizacji OS01..OS77
_osip = [f'OS{str(i+1).zfill(2)}' for i in range(77)]
# Stanowiska produkcyjne BB01..BB24, MZ01..MZ06
_bb = [f'BB{str(i+1).zfill(2)}' for i in range(24)]
_mz = ['MZ01', 'MZ02', 'MZ03', 'MZ04', 'MZ05', 'MZ06', 'MZ05-01', 'MZ06-01']

LOKALIZACJE_SZCZEGOLOWE = {
    'Magazyny': LOKALIZACJE_ZRODLO,
    'Regał R04': _r04,
    'Regał R05': _r05,
    'Regał R06': _r06,
    'Regał R07': _r07,
    'OSIP (OS01-OS77)': _osip,
    'Stanowiska BB': _bb,
    'Stanowiska MZ': _mz,
}

# Płaska lista na potrzeby selecta źródło/cel
LOKALIZACJE = sorted(list(set(LOKALIZACJE_ZRODLO + ['R04', 'R05', 'R06', 'R07', 'PSD01'])))
LOKALIZACJE_CEL = ['BF_MS01', 'BF_MP01', 'MS01', 'MP01', 'PSD01']
BUFORY = ['BF_MS01', 'BF_MP01']


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
