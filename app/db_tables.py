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

# Shared tables do not change their physical identifier with the production
# line.  They are nevertheless kept on an explicit allowlist because MySQL
# identifiers cannot be passed as query parameters.
_SHARED_ALLOWED_TABLES = {
    'magazyn_surowce',
    'magazyn_opakowania',
    'magazyn_dodatki',
    'raporty_koncowe',
}

_ALLOWED_BASE_TABLES = set(AGRO_TABLE_MAP) | _SHARED_ALLOWED_TABLES
_SHARED_LINE_CONTEXTS = {'PSD', 'AGRO', 'OSIP', 'ALL', ''}


def resolve_table_name(base_table, linia='PSD'):
    """Resolve a known logical table name without reflecting user input into SQL.

    Dynamic table names are accepted only when both the logical table and the
    line context are known.  Shared inventory/report tables may be requested
    from PSD, AGRO or OSIP but always resolve to the same physical identifier.
    Line-specific production tables keep the PSD/AGRO mapping and reject OSIP.
    """
    normalized_base = str(base_table or '').strip()
    if normalized_base == 'zasypy':
        normalized_base = 'szarze'

    if normalized_base not in _ALLOWED_BASE_TABLES:
        raise ValueError(f'Niedozwolona logiczna nazwa tabeli: {normalized_base!r}')

    normalized_line = str(linia or 'PSD').strip().upper()

    if normalized_base in _SHARED_ALLOWED_TABLES:
        if normalized_line in _SHARED_LINE_CONTEXTS:
            return normalized_base
        raise ValueError(f'Niedozwolona linia produkcyjna: {normalized_line!r}')

    if normalized_line == 'AGRO':
        return AGRO_TABLE_MAP[normalized_base]
    if normalized_line in ('PSD', 'ALL', ''):
        return normalized_base

    # Unknown line values must never affect identifier selection.
    raise ValueError(f'Niedozwolona linia produkcyjna: {normalized_line!r}')
