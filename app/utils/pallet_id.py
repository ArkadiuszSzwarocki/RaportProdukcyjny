import re
import threading
import time

_PALLET_ID_RE = re.compile(r'^[A-Z]{3}\d{18}$')
_PALLET_ID_LOCK = threading.Lock()
_LAST_EPOCH_MS = 0


def _resolve_prefix(linia, pallet_type='wyrób gotowy'):
    pallet_type = str(pallet_type or '').strip().lower()
    if pallet_type == 'surowiec':
        return 'SUR'
    if pallet_type == 'opakowanie':
        return 'OPK'
    if pallet_type == 'dodatek':
        return 'DOD'
    return 'PSD' if str(linia or '').upper() == 'PSD' else 'AGR'


def _next_epoch_ms():
    global _LAST_EPOCH_MS
    now_ms = int(time.time() * 1000)
    with _PALLET_ID_LOCK:
        if now_ms <= _LAST_EPOCH_MS:
            now_ms = _LAST_EPOCH_MS + 1
        _LAST_EPOCH_MS = now_ms
    return now_ms


def is_valid_pallet_id(value):
    return bool(_PALLET_ID_RE.match(str(value or '').strip().upper()))


def generate_pallet_id(linia, type='wyrób gotowy', record_id=None):
    # record_id kept for backward compatible signature.
    prefix = _resolve_prefix(linia, type)
    epoch_ms = _next_epoch_ms()
    return f"{prefix}{epoch_ms:018d}"
