from unittest.mock import MagicMock, patch

from app.repositories.picking_repository import PickingRepository


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
        ok, msg = service.delete_picking_order('PICK-20260930-001')
        assert ok is True
        assert 'została usunięta' in msg

