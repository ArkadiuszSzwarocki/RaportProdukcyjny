"""Quantity discrepancies, recorded inside the receipt transaction."""
import json
import math
import uuid
from decimal import Decimal, InvalidOperation

from app.utils.pallet_id import generate_pallet_id
from app.services.warehouse_history.movement_recorder import MovementRecorder


def receipt_quantity(declared, received, reason):
    try:
        original = Decimal(str(declared))
        actual = original if received is None else Decimal(str(received).replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError('Podaj prawidłową ilość przyjęcia.')
    if not original.is_finite() or not actual.is_finite() or actual <= 0 or actual > original:
        raise ValueError('Ilość przyjęta musi być większa od 0 i nie może przekraczać ilości wydanej.')
    if actual != actual.quantize(Decimal('0.001')):
        raise ValueError('Ilość przyjęta może mieć najwyżej trzy miejsca po przecinku.')
    difference = original - actual
    if difference and not str(reason or '').strip():
        raise ValueError('Wpisz powód różnicy ilości przy przyjęciu.')
    return float(actual), float(difference)


def require_issuer(item, login):
    issuer = item.get('return_approval_login')
    if not issuer or str(issuer).casefold() == str(login).casefold():
        return
    from flask import has_request_context, session
    if has_request_context() and str(session.get('rola') or session.get('role') or '').lower() == 'masteradmin':
        return
    raise ValueError(f'Różnicę musi zatwierdzić wydający: {issuer}.')


def prepare_difference(cursor, document, item, table, number, declared, difference, source):
    """Validate before the first stock write and retain metadata for the child."""
    allowed = {'magazyn_surowce', 'magazyn_opakowania', 'magazyn_agro_opakowania',
               'magazyn_dodatki', 'magazyn_palety', 'magazyn_palety_agro'}
    if table not in allowed:
        raise ValueError('Nieobsługiwane źródło palety.')
    if item.get('return_approval_login'):
        raise ValueError('Zwrot różnicy zatwierdź w całości; kolejna korekta wymaga wyjaśnienia z wydającym.')
    if not document.get('created_by') or not source or source in {'WIELE', 'DOSTAWA', 'PRODUKCJA', 'MAGAZYN'}:
        raise ValueError('Brak jednoznacznego wydającego lub miejsca zwrotu. Uzupełnij dokument źródłowy.')
    # Partial receipt must be atomic even on older installations.
    cursor.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() '
                   'AND TABLE_NAME IN (%s,%s,%s)', (table, 'magazyn_dostawy', 'palety_historia'))
    engines = cursor.fetchall()
    if len(engines) != 3 or any(str(row['ENGINE']).upper() != 'INNODB' for row in engines):
        raise ValueError('Częściowe przyjęcie wymaga tabel transakcyjnych InnoDB.')
    cursor.execute(f'SELECT * FROM {table} WHERE nr_palety=%s FOR UPDATE', (number,))
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise ValueError('Nie można jednoznacznie odczytać palety do rozliczenia różnicy.')
    row = dict(rows[0])
    qty_column = 'waga_netto' if table.startswith('magazyn_palety') else 'stan_magazynowy'
    if not math.isclose(float(row.get(qty_column) or 0), float(declared), abs_tol=0.0005):
        raise ValueError('Stan palety różni się od dokumentu. Najpierw wyjaśnij wcześniejsze ruchy palety.')
    return row, qty_column


def create_difference(cursor, connection, document, item, table, snapshot, source, destination,
                      declared, accepted, difference, reason, login, pallet_type):
    row, qty_column = snapshot
    child = {key: value for key, value in row.items()
             if key not in {'id', 'created_at', 'updated_at'} and key.replace('_', '').isalnum()}
    number = generate_pallet_id(document['linia'], pallet_type)
    child.update(nr_palety=number, lokalizacja='OCZEKUJĄCE', is_blocked=1)
    child[qty_column] = difference
    columns = list(child)
    cursor.execute(f"INSERT INTO {table} ({','.join('`'+key+'`' for key in columns)}) "
                   f"VALUES ({','.join(['%s']*len(columns))})", tuple(child[key] for key in columns))
    child_id = cursor.lastrowid
    return_id = str(uuid.uuid4())
    returned = dict(item)
    for key in ('accepted_at', 'accepted_by', 'rejected_at', 'rejected_by', 'lokalizacja_przyjecia',
                'putaway_confirmed_at', 'putaway_confirmed_by', 'putaway_confirmed_location',
                'putaway_suggested_location', 'pallet_status'):
        returned.pop(key, None)
    returned.update(id=str(uuid.uuid4()), nr_palety=number, sourcePalletNo=number,
                    sourcePalletId=child_id, sourceTable=table, sourceSpot=destination,
                    targetSpot=source, quantity=difference, netWeight=difference,
                    unitsPerPallet=difference, accepted=False, rejected=False, is_return=True,
                    return_approval_login=document['created_by'], return_origin_doc_id=document['id'],
                    return_reason=reason, return_parent_sscc=item.get('nr_palety'),
                    return_to_staging=(source == 'RAMPA'))
    cursor.execute("INSERT INTO magazyn_dostawy (id,order_ref,supplier,delivery_date,status,items,"
                   "created_by,created_at,requires_lab,linia,lokalizacja_z,lokalizacja_do) "
                   "VALUES (%s,%s,%s,NOW(),'OCZEKUJE',%s,%s,NOW(),0,%s,%s,%s)",
                   (return_id, 'ROZNICA-' + return_id[:8], 'PRZESUNIECIE — ZWROT RÓŻNICY',
                    json.dumps([returned], ensure_ascii=False, default=str), login, document['linia'], destination, source))
    item.update(original_quantity=declared, accepted_quantity=accepted, unaccepted_quantity=difference,
                quantity_reason=reason, return_document_id=return_id, return_pallet_sscc=number,
                return_approval_login_original=document['created_by'])
    for key in ('quantity', 'netWeight', 'unitsPerPallet', 'ilosc', 'currentWeight', 'weight'):
        if key in item:
            item[key] = accepted
    comment = (f'Różnica przyjęcia: wydano {declared:g}, przyjęto {accepted:g}, '
               f'nie przyjęto {difference:g}. Zwrot do {source}, zatwierdza {document["created_by"]}. '
               f'Paleta źródłowa {item.get("nr_palety")}; dokument {return_id}. Powód: {reason}')
    if not MovementRecorder.record_movement(child_id, document['linia'], pallet_type,
            'ZWROT_ROZNICY', destination, 'OCZEKUJĄCE', comment, login, number,
            cursor=cursor, connection=connection, operation_id=f'receipt-difference:{return_id}',
            quantity_before=0, quantity_after=difference):
        raise RuntimeError('Nie udało się zapisać historii różnicy przyjęcia.')
    return return_id


def difference_note(item):
    if not item.get('unaccepted_quantity'):
        return ''
    return (f"Wydano: {item.get('original_quantity')}; przyjęto: {item.get('accepted_quantity')}; "
            f"nie przyjęto: {item.get('unaccepted_quantity')}. "
            f"Zwrot: {item.get('return_document_id')}. Powód: {item.get('quantity_reason', '')}")
