"""Regression scenarios for transfer document integrity."""
import json
from unittest.mock import MagicMock

import pytest

from app.services.magazyn_dostawy.commands import live_transfer_service as module
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService


@pytest.fixture
def transfer_db(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {'id': 'doc', 'status': 'OCZEKUJE', 'items': '[]'}
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    locks = MagicMock()
    monkeypatch.setattr(module.PalletLockManager, 'set_pallets_blocked', locks)
    return conn, cursor, locks


@pytest.mark.parametrize('status', ['COMPLETED', 'CANCELLED', 'SZKIC', 'PUTAWAY_IN_PROGRESS'])
@pytest.mark.parametrize('operation', ['add', 'remove'])
def test_cannot_edit_terminal_or_other_workflow(transfer_db, status, operation):
    conn, cursor, locks = transfer_db
    cursor.fetchone.return_value['status'] = status
    service = module.LiveTransferService
    result = (service.add_live_transfer_item('doc', {'nr_palety': 'P1'}) if operation == 'add'
              else service.remove_live_transfer_item('doc', nr_palety='P1'))
    assert result[0] is False
    conn.commit.assert_not_called()
    locks.assert_not_called()
    assert 'FOR UPDATE' in cursor.execute.call_args_list[0].args[0]


def test_add_after_removal_has_unique_id_and_returns_it_to_browser(transfer_db):
    conn, cursor, _ = transfer_db
    cursor.fetchone.return_value['items'] = json.dumps([
        {'id': '0', 'sourcePalletId': 51, 'nr_palety': 'P1'},
        {'id': '2', 'sourcePalletId': 53, 'nr_palety': 'P3'},
    ])
    ok, result = module.LiveTransferService.add_live_transfer_item(
        'doc', {'nr_palety': 'P4', 'sourcePalletId': 54, 'rejected': True,
                'putaway_confirmed_at': 'forged'})
    assert ok
    assert len({item['id'] for item in result['items']}) == 3
    assert result['item_id'] == result['items'][-1]['id']
    assert not result['items'][-1]['rejected']
    assert 'putaway_confirmed_at' not in result['items'][-1]
    conn.commit.assert_called_once()


def test_remove_uses_document_item_id_even_if_zero(transfer_db):
    _, cursor, locks = transfer_db
    cursor.fetchone.return_value['items'] = json.dumps([
        {'id': '0', 'sourcePalletId': 51, 'nr_palety': 'P1'},
        {'id': '1', 'sourcePalletId': 52, 'nr_palety': 'P2'},
    ])
    ok, result = module.LiveTransferService.remove_live_transfer_item('doc', item_id=0)
    assert ok
    assert [item['nr_palety'] for item in result['items']] == ['P2']
    assert locks.call_args.args[1][0]['sourcePalletId'] == 51


@pytest.mark.parametrize('flag', ['accepted', 'rejected', 'putaway_confirmed_at'])
def test_cannot_remove_processed_item(transfer_db, flag):
    conn, cursor, locks = transfer_db
    cursor.fetchone.return_value['items'] = json.dumps([{'id': '0', 'nr_palety': 'P1', flag: True}])
    assert not module.LiveTransferService.remove_live_transfer_item('doc', item_id='0')[0]
    conn.commit.assert_not_called()
    locks.assert_not_called()


@pytest.mark.parametrize('items', [[], [{'id': '0', 'accepted': False}]])
def test_close_refuses_empty_or_unreceived_transfer(transfer_db, items):
    conn, cursor, locks = transfer_db
    cursor.fetchone.return_value['items'] = json.dumps(items)
    assert not module.LiveTransferService.close_live_transfer('doc')[0]
    conn.commit.assert_not_called()
    locks.assert_not_called()


def test_close_completed_is_idempotent_and_preserves_new_locks(transfer_db):
    conn, cursor, locks = transfer_db
    cursor.fetchone.return_value['status'] = 'COMPLETED'
    assert module.LiveTransferService.close_live_transfer('doc')[0]
    locks.assert_not_called()
    conn.commit.assert_not_called()


def test_close_resolved_transfer_preserves_quality_and_later_reservations(transfer_db):
    conn, cursor, locks = transfer_db
    cursor.fetchone.return_value['items'] = json.dumps([
        {'id': 'a', 'accepted': True}, {'id': 'b', 'rejected': True}])
    assert module.LiveTransferService.close_live_transfer('doc')[0]
    conn.commit.assert_called_once()
    locks.assert_not_called()


@pytest.mark.parametrize('status', ['CANCELLED', 'COMPLETED'])
@pytest.mark.parametrize('operation', ['accept', 'reject'])
def test_closed_delivery_cannot_receive_or_reject(monkeypatch, status, operation):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {'status': status}
    monkeypatch.setattr('app.services.magazyn_dostawy.acceptance_service.get_db_connection', lambda: conn)
    method = AcceptanceService.accept_item if operation == 'accept' else AcceptanceService.reject_item
    result = method('doc', 'item', 'MS01')
    assert not result[0]
    conn.commit.assert_not_called()
    assert 'FOR UPDATE' in cursor.execute.call_args.args[0]
