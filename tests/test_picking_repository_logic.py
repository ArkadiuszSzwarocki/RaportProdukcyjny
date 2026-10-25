from unittest.mock import MagicMock, patch

from app.repositories.picking_repository import PickingRepository
import pytest


def test_auto_complete_uses_sscc_instead_of_overlapping_table_ids():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.rowcount = 1
    assert PickingRepository.auto_complete_pallet_if_pending(7, 'SOY-SSCC', external_conn=connection) == 1
    sql, params = cursor.execute.call_args.args
    assert 'paleta_id = %s' not in sql
    assert 'SOY-SSCC' in params
    connection.commit.assert_not_called()
    connection.close.assert_not_called()


def test_auto_complete_failure_is_reported_to_movement_transaction():
    connection = MagicMock()
    connection.cursor.return_value.execute.side_effect = RuntimeError('write failed')
    with pytest.raises(RuntimeError, match='write failed'):
        PickingRepository.auto_complete_pallet_if_pending(nr_palety='SOY-SSCC', external_conn=connection)
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()


def test_standalone_auto_complete_commits_and_closes_its_connection():
    connection = MagicMock()
    connection.cursor.return_value.rowcount = 1
    with patch('app.repositories.picking_repository.get_db_connection', return_value=connection):
        assert PickingRepository.auto_complete_pallet_if_pending(nr_palety='SOY-SSCC') == 1
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


def test_get_active_orders_keeps_unresolved_shortage_placeholders_active():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch('app.repositories.picking_repository.get_db_connection', return_value=connection):
        PickingRepository.get_active_orders()

    sql = cursor.execute.call_args.args[0]
    assert "status = 'POMINIETA' AND paleta_id = 0" in sql
    assert 'pending_items > 0 OR shortage_items > 0' in sql


def test_cancel_order_cancels_pending_pallets_and_shortage_placeholders():
    cursor = MagicMock()
    cursor.rowcount = 2
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch('app.repositories.picking_repository.get_db_connection', return_value=connection):
        updated = PickingRepository.cancel_order('PICK-20260930-001-ABCD')

    assert updated == 2
    sql, params = cursor.execute.call_args.args
    assert "status = 'OCZEKUJE'" in sql
    assert "status = 'POMINIETA' AND paleta_id = 0" in sql
    assert params[1] == 'PICK-20260930-001-ABCD'
    connection.commit.assert_called_once()


def test_next_sequence_uses_max_not_count_so_deleted_numbers_are_not_reused():
    cursor = MagicMock()
    cursor.fetchone.return_value = {'max_seq': 7}
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch('app.repositories.picking_repository.get_db_connection', return_value=connection):
        sequence = PickingRepository.get_next_order_sequence()

    assert sequence == 8
    sql = cursor.execute.call_args.args[0]
    assert 'MAX(' in sql
    assert 'COUNT(' not in sql
    assert 'SUBSTRING_INDEX' in sql


def test_picking_service_cancel_and_delete_order():
    from app.services.picking_service import PickingService

    service = PickingService()

    with patch.object(PickingRepository, 'get_by_order_ref', return_value=[{'id': 1, 'status': 'OCZEKUJE'}]), \
         patch.object(PickingRepository, 'cancel_order', return_value=1):
        ok, msg = service.cancel_picking_order('PICK-20260930-001')
        assert ok is True
        assert 'Anulowano 1 pozycji' in msg

    with patch.object(PickingRepository, 'get_by_order_ref', return_value=[{'id': 1, 'status': 'OCZEKUJE'}]), \
         patch.object(PickingRepository, 'delete_order', return_value=1):
        ok, msg = service.delete_picking_order('PICK-20260930-001', user_role='pracownik')
        assert ok is True
        assert 'została usunięta' in msg


@pytest.mark.parametrize('role', [None, 'laborant'])
def test_delete_picking_order_denies_missing_or_unauthorized_role(role):
    from app.services.picking_service import PickingService
    with patch.object(PickingRepository, 'delete_order') as delete:
        assert PickingService().delete_picking_order('PICK-20260930-001', user_role=role)[0] is False
    delete.assert_not_called()
