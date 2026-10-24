"""Production returns receive their new pallet, never the original station pallet."""
import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch
import pytest
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService


@pytest.mark.parametrize('case', ['valid', 'missing_stock', 'explicit_destination', 'zero_quantity'])
@pytest.mark.parametrize('station', ['BB03', 'MZ07'])
@pytest.mark.parametrize('supplier', ['PRODUKCJA', ''])
def test_receive_existing_station_return_without_touching_parent(station, supplier, case):
    item = dict(id='22', pallet_id='22', sourcePalletId=11, sourcePalletNo='MOTHER',
                nr_palety='RETURN', sourceSpot=station, is_return=True,
                productName='Test material', quantity=150, netWeight=150, unit='kg')
    document = dict(id='return-doc', supplier=supplier, linia='AGRO', status='OCZEKUJE',
                    lokalizacja_z=station, lokalizacja_do='MAGAZYN', items=json.dumps([item]))
    if case == 'explicit_destination':
        document['lokalizacja_do'] = 'MS01'
    if case == 'zero_quantity':
        item.update(quantity=0, netWeight=0)
        document['items'] = json.dumps([item])
    conn = MagicMock()
    cursor = conn.cursor.return_value
    def one():
        sql, params = cursor.execute.call_args.args
        if 'SELECT * FROM magazyn_dostawy' in sql:
            return document
        if 'SELECT id FROM magazyn_surowce' in sql and params == ('RETURN',):
            return {'id': 22}
        if 'SELECT id FROM magazyn_surowce' in sql and params == ('MOTHER',):
            return {'id': 11}
        return None
    def all_rows():
        sql = cursor.execute.call_args.args[0]
        if 'FROM magazyn_surowce' in sql:
            return [] if case == 'missing_stock' else [{'id': 22, 'stan_magazynowy': 150}]
        return []
    cursor.fetchone.side_effect = one
    cursor.fetchall.side_effect = all_rows
    with ExitStack() as stack:
        for name, value in {
            'app.services.magazyn_dostawy.acceptance_service.get_db_connection': conn,
            'app.utils.location_validator.validate_registered_warehouse_location': (True, None),
            'app.utils.pallet_receipt_rules.lock_receipt_registry': None,
            'app.utils.pallet_receipt_rules.ensure_unique_stock_code': 'RETURN',
            'app.utils.surowiec_validator.is_valid_surowiec': True,
            'app.services.magazyn_dostawy.acceptance_service.PalletLockManager.has_quality_or_manual_block': False,
            'app.services.magazyn_dostawy.acceptance_service.PalletLockManager.set_pallets_blocked': None,
            'app.services.magazyn_dostawy.acceptance_service.MovementRecorder.record_movement': True,
            'app.repositories.movement_document_repository.MovementDocumentRepository.queue_completed': None,
        }.items():
            stack.enter_context(patch(name, return_value=value))
        result = AcceptanceService.accept_item('return-doc', '22', 'MP01', 'test-operator')
    if case != 'valid':
        assert not result[0]
        conn.commit.assert_not_called()
        assert not any(call.args[0].strip().startswith(('UPDATE magazyn_surowce', 'INSERT INTO magazyn_surowce'))
                       for call in cursor.execute.call_args_list)
        return
    assert result[0], result[1]
    conn.commit.assert_called_once()
    updates = [(call.args[0], call.args[1]) for call in cursor.execute.call_args_list
               if call.args[0].strip().startswith('UPDATE magazyn_surowce')]
    assert len(updates) == 1
    assert updates[0][1][-1] == 22
    assert not any(call.args[0].strip().startswith('INSERT INTO magazyn_surowce') for call in cursor.execute.call_args_list)
    saved = [call.args[1][0] for call in cursor.execute.call_args_list
             if call.args[0].strip().startswith('UPDATE magazyn_dostawy')]
    assert json.loads(saved[0])[0]['sourcePalletId'] == 22
