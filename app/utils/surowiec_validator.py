"""
Validator for raw material names against the dictionary (slownik_surowcow).

Ensures that only recognized raw materials can be accepted, moved,
transferred, ordered, or calculated in the system.
"""
from app.core.database import get_db_connection


_CACHED_RAW_NAMES = None
_CACHED_NORM_NAMES = None
_CACHE_TS = 0


class SurowiecDictionaryUnavailable(RuntimeError):
    """Raised when the raw-material dictionary cannot be read safely."""


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
    """Load valid raw-material names from ``slownik_surowcow``.

    A database/read failure is different from a successfully loaded empty
    dictionary.  Both must fail closed for validation, but callers may need to
    show a different message to the operator.
    """
    global _CACHED_RAW_NAMES, _CACHED_NORM_NAMES, _CACHE_TS
    import time
    now = time.time()

    if _CACHED_RAW_NAMES is not None and (now - _CACHE_TS) < 120:
        return _CACHED_RAW_NAMES, _CACHED_NORM_NAMES

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
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
    except Exception as exc:
        # Never convert a database outage into "allow every material".
        invalidate_cache()
        raise SurowiecDictionaryUnavailable(
            'Nie udało się odczytać słownika surowców.'
        ) from exc
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def invalidate_cache():
    """Force a reload of the dictionary on the next validation call."""
    global _CACHED_RAW_NAMES, _CACHED_NORM_NAMES, _CACHE_TS
    _CACHED_RAW_NAMES = None
    _CACHED_NORM_NAMES = None
    _CACHE_TS = 0


def _matches_dictionary(name, raw_names, norm_names):
    clean = str(name).strip().lower()
    if clean in raw_names:
        return True
    norm = _norm_surowiec(clean)
    return bool(norm and norm in norm_names)


def is_valid_surowiec(name):
    """Return True only when the name is positively verified in the dictionary."""
    if not name or not str(name).strip():
        return False

    try:
        raw_names, norm_names = _load_dictionary_names()
    except SurowiecDictionaryUnavailable:
        return False

    # A successfully loaded but empty dictionary is not permission to bypass
    # validation. It means no raw material can currently be verified.
    if not raw_names:
        return False

    return _matches_dictionary(name, raw_names, norm_names)


def validate_surowiec_name(name):
    """Validate a raw-material name and return ``(is_valid, error_message)``."""
    if not name or not str(name).strip():
        return False, "Nazwa surowca jest wymagana."

    clean = str(name).strip()
    try:
        raw_names, norm_names = _load_dictionary_names()
    except SurowiecDictionaryUnavailable:
        return False, (
            "Nie można teraz zweryfikować surowca w słowniku. "
            "Operacja została bezpiecznie wstrzymana — spróbuj ponownie po przywróceniu połączenia z bazą."
        )

    if not raw_names:
        return False, (
            "Słownik surowców jest pusty. Operacja została wstrzymana — "
            "dodaj poprawne pozycje do słownika przed użyciem."
        )

    if not _matches_dictionary(clean, raw_names, norm_names):
        return False, (
            f"Surowiec '{clean}' nie istnieje w słowniku surowców. "
            f"Operacja odrzucona — dodaj surowiec do słownika przed użyciem."
        )

    return True, ""


def validate_surowiec_list(names):
    """Validate all names against the raw-material dictionary."""
    if not names:
        return True, ""

    for name in names:
        is_valid, error = validate_surowiec_name(name)
        if not is_valid:
            return False, error

    return True, ""
