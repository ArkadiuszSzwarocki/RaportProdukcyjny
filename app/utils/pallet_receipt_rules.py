"""Shared validation for pallet registration and receipt; no implicit data repair."""
from datetime import date, datetime


STOCK_TABLES = {
    'magazyn_surowce': ('stan_magazynowy', 'nazwa', 'Surowiec'),
    'magazyn_agro_surowce': ('stan_magazynowy', 'nazwa', 'Surowiec'),
    'magazyn_opakowania': ('stan_magazynowy', 'nazwa', 'Opakowanie'),
    'magazyn_agro_opakowania': ('stan_magazynowy', 'nazwa', 'Opakowanie'),
    'magazyn_dodatki': ('stan_magazynowy', 'nazwa', 'Dodatek'),
    'magazyn_palety': ('waga_netto', 'produkt', 'Wyrób Gotowy'),
}


def stock_tables(cursor):
    # Historical views must not count the same physical stock twice.
    cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.TABLES "
                   "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'")
    present = {row['name'] for row in cursor.fetchall()}
    required = {'magazyn_surowce', 'magazyn_opakowania', 'magazyn_dodatki', 'magazyn_palety'}
    if not required.issubset(present):
        raise ValueError('Nie można sprawdzić kompletu kartotek magazynowych.')
    return [(table, *columns) for table, columns in STOCK_TABLES.items() if table in present]


def stock_at_location(cursor, location, *, excluding=None, lock=False):
    items = []
    for table, quantity, name, kind in stock_tables(cursor):
        query = (f'SELECT nr_palety, {name} AS nazwa, {quantity} AS stan_magazynowy '
                 f'FROM {table} WHERE lokalizacja=%s AND {quantity}>0')
        params = [location]
        if excluding:
            query += ' AND (nr_palety IS NULL OR UPPER(TRIM(nr_palety))<>%s)'
            params.append(str(excluding).strip().upper())
        cursor.execute(query + (' FOR UPDATE' if lock else ''), tuple(params))
        items.extend(dict(row, typ=kind, product_name=row['nazwa']) for row in cursor.fetchall())
    return items


def lock_receipt_registry(cursor):
    # Shared transaction locks, also used by rack writes. No session locks or DDL.
    cursor.execute("SELECT ENGINE AS engine FROM information_schema.TABLES "
                   "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='magazyn_dozwolone_lokalizacje'")
    registry = cursor.fetchone()
    if not registry or str(registry['engine']).casefold() != 'innodb':
        raise ValueError('Wspólna kontrola przyjęć wymaga transakcyjnego słownika lokalizacji InnoDB.')
    cursor.execute('SELECT nazwa FROM magazyn_dozwolone_lokalizacje ORDER BY nazwa FOR UPDATE')
    if not cursor.fetchall():
        raise ValueError('Słownik lokalizacji jest pusty. Uzupełnij ustawienia magazynu.')


def ensure_unique_stock_code(cursor, code, *, exclude=None, active_only=True):
    code = str(code or '').strip().upper()
    if not code:
        raise ValueError('Numer palety / SSCC jest wymagany.')
    lock_receipt_registry(cursor)
    for table, quantity, _name, _kind in stock_tables(cursor):
        query = f'SELECT id FROM {table} WHERE UPPER(TRIM(nr_palety))=%s'
        params = [code]
        if active_only:
            query += f' AND {quantity}>0'
        if exclude and table == exclude[0]:
            query += ' AND id<>%s'
            params.append(exclude[1])
        cursor.execute(query + ' FOR UPDATE', tuple(params))
        if cursor.fetchall():
            raise ValueError(f'Paleta {code} już istnieje w kartotece {table}. Nie można powielić SSCC.')
    return code


def parse_pallet_date(value):
    if value is None or str(value).strip() == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ('%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError(f'Nieprawidłowa data: {text}. Użyj RRRR-MM-DD.')


def validate_pallet_dates(production, expiry):
    production, expiry = parse_pallet_date(production), parse_pallet_date(expiry)
    if production and production > date.today():
        raise ValueError('Data produkcji nie może być późniejsza niż dzisiejsza.')
    if production and expiry and expiry < production:
        raise ValueError('Data przydatności nie może być wcześniejsza niż data produkcji.')
    return (production.isoformat() if production else None,
            expiry.isoformat() if expiry else None)


def delivery_pallet_type(item):
    aliases = {'surowiec': 'surowiec', 'opakowanie': 'opakowanie', 'dodatek': 'dodatek',
               'wyrob_gotowy': 'wyrob_gotowy', 'wyrób gotowy': 'wyrob_gotowy',
               'wyrob gotowy': 'wyrob_gotowy', 'magazyn': 'wyrob_gotowy', 'produkcja': 'wyrob_gotowy'}
    explicit = [str(item.get(key) or '').strip().casefold()
                for key in ('scannedType', 'type', 'palletType') if item.get(key)]
    resolved = {aliases.get(value) for value in explicit}
    if None in resolved or len(resolved) > 1:
        raise ValueError('Nieznany lub sprzeczny typ palety dostawy.')
    if resolved:
        return resolved.pop()
    # Compatibility with older forms that did not send a dedicated type.
    packaging = str(item.get('packageForm') or '').strip().casefold()
    return 'opakowanie' if packaging in ('packaging', 'tasma', 'taśma', 'karton') or str(item.get('unit') or '').casefold() == 'szt' else 'surowiec'


# A production record is historical once it was converted, consumed or closed.
# Its original weight is production history, not available warehouse stock.
FINAL_PRODUCTION_PALLET_STATUSES = (
    'przyjeta', 'w_magazynie', 'zamknieta', 'przeklasyfikowana',
    'zuzyta', 'zuzyte', 'zarchiwizowana', 'archiwalna', 'usunieta',
)


def production_receipt_block_reason(status):
    value = str(status or '').strip().lower()
    if value == 'przeklasyfikowana':
        return 'Ta paleta została już przeklasyfikowana na surowiec. Nie można przyjąć jej ponownie. Sprawdź aktualny stan surowca po numerze SSCC.'
    if value in FINAL_PRODUCTION_PALLET_STATUSES and value not in ('przyjeta', 'w_magazynie'):
        return 'Paleta została już zużyta, zamknięta lub zarchiwizowana. Ponowne przyjęcie jest zablokowane.'
    return None
