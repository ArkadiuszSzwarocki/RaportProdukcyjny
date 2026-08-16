from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, List, Optional, Tuple


ETAP_MIN = 1
ETAP_MAX = 6


def _norm_linia(linia: Optional[str]) -> str:
    linia_value = str(linia or 'PSD').upper()
    return 'AGRO' if linia_value == 'AGRO' else 'PSD'


def _visible_etaps_for_linia(linia: str) -> List[int]:
    if _norm_linia(linia) == 'AGRO':
        return [1, 2, 3, 4, 5]
    return list(range(ETAP_MIN, ETAP_MAX + 1))


def _is_valid_etap_for_linia(etap_nr: int, linia: str) -> bool:
    linia_u = _norm_linia(linia)
    if linia_u == 'AGRO':
        if etap_nr in [1, 2, 3, 4, 5]:
            return True
        try:
            etap_s = str(int(etap_nr))
            if len(etap_s) > 1 and etap_s[0] in ['3', '4']:
                return True
        except Exception:
            pass
        return False
    return etap_nr in _visible_etaps_for_linia(linia)


def _format_hhmm(dt: Any) -> str:
    if not dt:
        return ''
    try:
        return dt.strftime('%H:%M')
    except Exception:
        try:
            value = str(dt)
            if ' ' in value and ':' in value:
                return value.split(' ')[1][:5]
            if ':' in value:
                return value[:5]
        except Exception:
            pass
    return ''


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return '0m'
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def _parse_hhmm_to_dt(target_date: date, hhmm: Optional[str]) -> Optional[datetime]:
    value = str(hhmm or '').strip()
    if not value:
        return None
    value = value.replace('.', ':')
    parts = value.split(':')
    if len(parts) < 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except Exception:
        return None
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    try:
        return datetime.combine(target_date, time(hour=hours, minute=minutes))
    except Exception:
        return None


def _agro_suffix_for_etap(etap_nr: int) -> Optional[int]:
    try:
        etap_str = str(int(etap_nr))
    except Exception:
        return None
    if len(etap_str) > 1 and etap_str[0] in ['3', '4']:
        try:
            return int(etap_str[1:])
        except Exception:
            return None
    return None


def _build_sequence_for_szarza(linia_u: str, existing_etaps: List[int], include_etap: Optional[int] = None) -> List[int]:
    if linia_u != 'AGRO':
        return list(range(ETAP_MIN, ETAP_MAX + 1))

    suffixes: set[int] = set()
    has_pair_stage = False
    for etap in existing_etaps:
        if etap in [3, 4]:
            has_pair_stage = True
        suffix = _agro_suffix_for_etap(etap)
        if suffix is not None:
            has_pair_stage = True
            suffixes.add(suffix)

    include_pair_stage = has_pair_stage
    if include_etap is not None:
        if include_etap in [3, 4]:
            include_pair_stage = True
        suffix = _agro_suffix_for_etap(include_etap)
        if suffix is not None:
            include_pair_stage = True
            suffixes.add(suffix)

    ordered: List[int] = [1, 2]
    if include_pair_stage:
        ordered.extend([3, 4])
        for suffix in sorted(suffixes):
            ordered.append(int(f'3{suffix}'))
            ordered.append(int(f'4{suffix}'))
    ordered.append(5)

    output: List[int] = []
    seen: set[int] = set()
    for etap in ordered:
        if etap in seen:
            continue
        seen.add(etap)
        output.append(etap)
    return output


def _prev_next_etap_in_sequence(seq: List[int], etap_nr: int) -> Tuple[Optional[int], Optional[int]]:
    try:
        idx = seq.index(int(etap_nr))
    except Exception:
        return None, None
    prev_etap = seq[idx - 1] if idx > 0 else None
    next_etap = seq[idx + 1] if idx + 1 < len(seq) else None
    return prev_etap, next_etap


def _etap_display_name(linia_u: str, etap_nr: int) -> str:
    etap = int(etap_nr)
    if linia_u == 'AGRO':
        if etap == 1:
            return 'Naważanie'
        if etap == 2:
            return 'Mieszanie i oczekiwanie na LAB'
        if etap == 3:
            return 'Dosypka'
        if etap == 4:
            return 'Mieszanie i oczekiwanie na LAB po dosypce'
        if etap == 5:
            return 'Opróżnianie'
        if 30 < etap < 40:
            return f'Dosypka ({etap})'
        if 40 < etap < 50:
            return f'Mieszanie po dosypce ({etap})'
        return f'Etap {etap}'

    if etap == 1:
        return 'Naważanie'
    if etap == 2:
        return 'Mieszanie'
    if etap == 3:
        return 'Oczekiwanie na LAB'
    if etap == 4:
        return 'Dosypka'
    if etap == 5:
        return 'Mieszanie'
    if etap == 6:
        return 'Opróżnianie'
    return f'Etap {etap}'


@dataclass(frozen=True)
class EtapRow:
    etap: int
    czas_start: Optional[datetime]
    czas_stop: Optional[datetime]
    start_login: Optional[str]
    stop_login: Optional[str]