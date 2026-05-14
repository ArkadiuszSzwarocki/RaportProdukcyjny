AGRO_TABLE_MAP = {
    'plan_produkcji': 'plan_produkcji_agro',
    'szarze': 'szarze_agro',
    'zasypy': 'szarze_agro',
    'dosypki': 'dosypki_agro',
    'palety_workowanie': 'palety_agro',
    'magazyn_palety': 'magazyn_palety_agro',
    'magazyn_ruch': 'magazyn_agro_ruch',
    'bufor': 'bufor_agro'
}


def resolve_table_name(base_table, linia='PSD'):
    if base_table == 'zasypy':
        base_table = 'szarze'
    

    if linia and str(linia).upper() == 'AGRO':
        return AGRO_TABLE_MAP.get(base_table, base_table)
    return base_table