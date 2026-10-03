# cspell:words neighbours sscc
"""Cancellation and reservation must identify a physical pallet exactly."""
import json
from unittest.mock import MagicMock

import pytest

from app.services.magazyn_dostawy.commands import delivery_cancellation_service as module
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager


def test_cancel_restores_only_exact_pallet_not_same_material_neighbours(monkeypatch):
    cursor = MagicMock()
    cursor.rowcount = 1
    row = {'id': 12, 'nr_palety': 'SSCC12', 'lokalizacja': 'BUF'}
    monkeypatch.setattr(module.InternalTransferProcessor, '_find_active_pallet_by_sscc',
                        lambda *args: (row, 'surowiec', 'magazyn_surowce'))
    module.DeliveryCancellationService.restore_buffered_items(cursor, [
        {'sourceSpot': 'BUF', 'originalSpot': 'MS01', 'productName': 'Same material',
         'nr_palety': 'SSCC12'}], 'AGRO', 'ORDER', 'user')
    sql, params = cursor.execute.call_args_list[0].args
    assert 'WHERE id = %s AND nr_palety = %s' in sql
    assert 'nazwa = ' not in sql
    assert params == ('MS01', 12, 'SSCC12', 'BUF')
    assert cursor.execute.call_args_list[1].args[1][:2] == (12, 'SSCC12')


def test_cancel_does_not_restore_received_or_rejected_items():
    cursor = MagicMock()
    module.DeliveryCancellationService.restore_buffered_items(cursor, [
        {'sourceSpot': 'BUF', 'originalSpot': 'MS01', 'accepted': True},
        {'sourceSpot': 'BUF', 'originalSpot': 'MS01', 'rejected': True},
    ], 'AGRO', 'ORDER', 'user')
    cursor.execute.assert_not_called()


def test_repeated_cancel_does_not_unblock_new_reservation(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'status': 'CANCELLED'}
    locks = MagicMock()
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(PalletLockManager, 'set_pallets_blocked', locks)
    assert module.DeliveryCancellationService.cancel_dostawa('doc')[0]
    locks.assert_not_called()
    conn.commit.assert_not_called()


def test_cancel_releases_only_pending_items(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    pending = {'id': 'b', 'nr_palety': 'P2'}
    conn.cursor.return_value.fetchone.return_value = {
        'status': 'OCZEKUJE', 'linia': 'AGRO', 'order_ref': 'ref',
        'items': json.dumps([{'id': 'a', 'accepted': True, 'nr_palety': 'P1'}, pending])}
    locks = MagicMock()
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(PalletLockManager, 'set_pallets_blocked', locks)
    assert module.DeliveryCancellationService.cancel_dostawa('doc')[0]
    assert locks.call_args.args[1] == [pending]


def test_stock_lock_uses_number_and_never_colliding_ids():
    cursor = MagicMock()
    cursor.fetchall.side_effect = lambda: (
        [{'id': 7, 'nr_palety': 'P1'}] if 'FROM magazyn_surowce ' in cursor.execute.call_args.args[0]
        else [])
    PalletLockManager.set_pallets_blocked(cursor, [{'sourcePalletId': 7, 'nr_palety': 'P1'}])
    updates = [call.args for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
    assert updates == [('UPDATE magazyn_surowce SET is_blocked = %s WHERE id = %s', (1, 7))]


def test_id_without_table_cannot_block_unrelated_pallets():
    cursor = MagicMock()
    with pytest.raises(ValueError):
        PalletLockManager.set_pallets_blocked(cursor, [{'sourcePalletId': 7}])
    cursor.execute.assert_not_called()


def test_ambiguous_number_is_rejected_before_any_lock_update():
    cursor = MagicMock()
    cursor.fetchall.return_value = [{'id': 7, 'nr_palety': 'P1'}]
    with pytest.raises(ValueError, match='Niejednoznaczna'):
        PalletLockManager.set_pallets_blocked(cursor, [{'nr_palety': 'P1'}])
    assert all(not call.args[0].startswith('UPDATE') for call in cursor.execute.call_args_list)


def test_connection_failure_is_not_silently_ignored():
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError('Connection lost')
    with pytest.raises(RuntimeError, match='Connection lost'):
        PalletLockManager.set_pallets_blocked(cursor, [{'nr_palety': 'P1'}])
