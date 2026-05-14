AGRO_TABLE_MAP = {
    'plan_produkcji': 'plan_produkcji_agro',
    'szarze': 'szarze_agro',
    'zasypy': 'szarze_agro',
    'dosypki': 'dosypki_agro',
    'palety_workowanie': 'palety_agro',
    'magazyn_palety': 'magazyn_palety_agro',
    'bufor': 'bufor_agro',
    'magazyn_surowce': 'magazyn_agro_surowce',
    'magazyn_opakowania': 'magazyn_agro_opakowania',
    'magazyn_ruch': 'magazyn_agro_ruch',
}


def resolve_table_name(base_table, linia='PSD'):
    if base_table == 'zasypy':
        base_table = 'szarze'
    if linia and str(linia).upper() == 'AGRO':
        return AGRO_TABLE_MAP.get(base_table, base_table)
    return base_table