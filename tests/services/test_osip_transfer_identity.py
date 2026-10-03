# cspell:words sscc
"""OSIP scans must use complete identity and preserve received stock."""
from unittest.mock import MagicMock

import pytest

from app.models.osip_transfer_model import OsipTransferModel
from app.models.osip_transfer_item_model import OsipTransferItemModel
from app.services import osip_transfer_service as module


@pytest.mark.parametrize('code', ['SSCC', '12345678', 'SSCC123456789EXTRA', ''])
def test_fragment_or_empty_code_cannot_receive_pallet(monkeypatch, code):
    repo = MagicMock()
    repo.get_transfer_by_id.return_value = OsipTransferModel(
        id=1, status='IN_TRANSIT', items=[OsipTransferItemModel(id=2, nr_palety='SSCC123456789')])
    connect = MagicMock()
    monkeypatch.setattr(module, 'get_db_connection', connect)
    with pytest.raises(ValueError):
        module.OsipTransferService(repo).receive_single_item(1, code, 'OSIP', 'user')
    connect.assert_not_called()


@pytest.mark.parametrize('status,item_status', [('CANCELLED', 'LOADED'), ('COMPLETED', 'RECEIVED'), ('IN_TRANSIT', 'RECEIVED')])
def test_repeat_or_closed_transfer_cannot_relocate_received_pallet(monkeypatch, status, item_status):
    repo = MagicMock()
    repo.get_transfer_by_id.return_value = OsipTransferModel(
        id=1, status=status, items=[OsipTransferItemModel(id=2, nr_palety='P1', status=item_status)])
    connect = MagicMock()
    monkeypatch.setattr(module, 'get_db_connection', connect)
    with pytest.raises(ValueError):
        module.OsipTransferService(repo).receive_single_item(1, 'P1', 'OSIP', 'user')
    connect.assert_not_called()


def test_partial_cancel_does_not_pull_received_pallet_back(monkeypatch):
    repo = MagicMock()
    repo.get_transfer_by_id.return_value = OsipTransferModel(
        id=1, source_warehouse='MS01', status='IN_TRANSIT', items=[
            OsipTransferItemModel(id=2, pallet_id=11, status='RECEIVED'),
            OsipTransferItemModel(id=3, pallet_id=12, status='LOADED')])
    conn = MagicMock()
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    move = MagicMock()
    monkeypatch.setattr(module.OsipTransferService, '_move_stock', move)
    module.OsipTransferService(repo).cancel_transfer(1, 'user')
    move.assert_called_once()
    assert move.call_args.args[3].pallet_id == 12
    assert move.call_args.args[4] == 'MS01'
    assert [call.args[1] for call in conn.cursor.return_value.execute.call_args_list] == [(3, 1)]
    repo.update_transfer_status.assert_called_once_with(1, 'CANCELLED', 'user', external_conn=conn)


def test_auto_receipt_uses_exact_code_and_refuses_multiple_transfers(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [{'id': 1}, {'id': 2}]
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    module.OsipTransferService.auto_receive_pallet_by_code('SSCC123456789', 'OSIP', 'user')
    sql, params = conn.cursor.return_value.execute.call_args.args
    assert 'LIKE' not in sql
    assert params == ('SSCC123456789', 0, 0)
    conn.commit.assert_not_called()
