"""
Validator for raw material names against the dictionary (slownik_surowcow).

Ensures that only recognized raw materials can be accepted, moved,
transferred, ordered, or calculated in the system.
"""
from app.core.database import get_db_connection


_CACHED_RAW_NAMES = None
_CACHED_NORM_NAMES = None
_CACHE_TS = 0


def _norm_surowiec(s):
    if not s:
        return ''
    import re
    s = str(s).strip().lower()
    repl = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'}
    for k, v in repl.items():
        s = s.replace(k, v)
    return re.sub(r'[^a-z0-9]', '', s)


def _load_dictionary_names():
    """Loads all valid raw material names from slownik_surowcow.

    Returns:
        tuple[set[str], set[str]]: (raw_names, norm_names).
    """
    global _CACHED_RAW_NAMES, _CACHED_NORM_NAMES, _CACHE_TS
    import time
    now = time.time()

    if _CACHED_RAW_NAMES is not None and (now - _CACHE_TS) < 120:
        return _CACHED_RAW_NAMES, _CACHED_NORM_NAMES

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT nazwa FROM slownik_surowcow "
            "WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''"
        )
        raw_names = set()
        norm_names = set()
        for row in cursor.fetchall():
            n = str(row.get('nazwa', '')).strip().lower()
            if n:
                raw_names.add(n)
                norm = _norm_surowiec(n)
                if norm:
                    norm_names.add(norm)
        _CACHED_RAW_NAMES = raw_names
        _CACHED_NORM_NAMES = norm_names
        _CACHE_TS = now
        return raw_names, norm_names
    except Exception:
        return set(), set()
    finally:
        conn.close()


def invalidate_cache():
    """Forces a reload of the dictionary on next validation call."""
    global _CACHED_RAW_NAMES, _CACHED_NORM_NAMES, _CACHE_TS
    _CACHED_RAW_NAMES = None
    _CACHED_NORM_NAMES = None
    _CACHE_TS = 0


def is_valid_surowiec(name):
    """Checks if a raw material name exists in slownik_surowcow.

    Args:
        name: Raw material name string.

    Returns:
        bool: True if the name exists in the dictionary.
    """
    if not name or not str(name).strip():
        return False

    clean = str(name).strip().lower()
    raw_names, norm_names = _load_dictionary_names()
    if not raw_names:
        return True

    if clean in raw_names:
        return True

    norm = _norm_surowiec(clean)
    if norm and norm in norm_names:
        return True

    return False


def validate_surowiec_name(name):
    """Validates a raw material name and returns a tuple (is_valid, error_message).

    Args:
        name: Raw material name to validate.

    Returns:
        tuple[bool, str]: (True, '') if valid, (False, error_message) if not.
    """
    if not name or not str(name).strip():
        return False, "Nazwa surowca jest wymagana."

    clean = str(name).strip()
    if not is_valid_surowiec(clean):
        return False, (
            f"Surowiec '{clean}' nie istnieje w słowniku surowców. "
            f"Operacja odrzucona — dodaj surowiec do słownika przed użyciem."
        )

    return True, ""


def validate_surowiec_list(names):
    """Validates a list of raw material names against the dictionary.

    Args:
        names: List of raw material name strings.

    Returns:
        tuple[bool, str]: (True, '') if all valid, (False, error for first invalid) if not.
    """
    if not names:
        return True, ""

    for name in names:
        is_valid, error = validate_surowiec_name(name)
        if not is_valid:
            return False, error

    return True, ""
