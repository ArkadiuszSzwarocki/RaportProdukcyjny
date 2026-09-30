"""Central allowlist for line-specific SQL table identifiers."""

AGRO_TABLE_MAP = {
    'plan_produkcji': 'plan_produkcji_agro',
    'szarze': 'szarze_agro',
    'zasypy': 'szarze_agro',
    'dosypki': 'dosypki_agro',
    'palety_workowanie': 'palety_agro',
    'magazyn_ruch': 'magazyn_agro_ruch',
    'bufor': 'bufor_agro',
    'magazyn_palety': 'magazyn_palety_agro',
}

# These inventory tables are shared or have their own repository-level mapping,
# but are still legitimate callers of get_table_name().  Keep the allowlist
# explicit so a request-controlled identifier can never become an SQL table.
_SHARED_ALLOWED_TABLES = {
    'magazyn_surowce',
    'magazyn_opakowania',
}

_ALLOWED_BASE_TABLES = set(AGRO_TABLE_MAP) | _SHARED_ALLOWED_TABLES


def resolve_table_name(base_table, linia='PSD'):
    """Resolve a known logical table name for PSD/AGRO.

    Table names cannot be parameterized by MySQL, so every dynamic identifier
    must come from this explicit allowlist.  Unknown input is rejected instead
    of being reflected into an f-string SQL statement.
    """
    normalized_base = str(base_table or '').strip()
    if normalized_base == 'zasypy':
        normalized_base = 'szarze'

    if normalized_base not in _ALLOWED_BASE_TABLES:
        raise ValueError(f'Niedozwolona logiczna nazwa tabeli: {normalized_base!r}')

    normalized_line = str(linia or 'PSD').strip().upper()
    if normalized_line == 'AGRO':
        return AGRO_TABLE_MAP.get(normalized_base, normalized_base)
    if normalized_line in ('PSD', 'ALL', ''):
        return normalized_base

    # Unknown line values must not silently affect identifier selection.
    raise ValueError(f'Niedozwolona linia produkcyjna: {normalized_line!r}')
