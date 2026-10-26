from unittest.mock import MagicMock, patch
import pytest
from app.services.auto_label_service import AutoLabelService


def test_existing_job_completes_intent_without_generating_another_label():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (12,)
    with patch('app.utils.pallet_label.prepare_pallet_label_data') as prepare:
        AutoLabelService.queue_for_pallet(conn, cursor, 55)
    prepare.assert_not_called()
    assert conn.commit.call_count == 2
    assert not any('INSERT' in call.args[0] for call in cursor.execute.call_args_list)


def test_no_label_data_does_not_mark_intent_queued():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    with patch('app.utils.pallet_label.prepare_pallet_label_data', return_value=None):
        with pytest.raises(RuntimeError, match='Brak danych'):
            AutoLabelService.queue_for_pallet(conn, cursor, 55)
    conn.commit.assert_not_called()
    assert not any(call.args[0].lstrip().startswith('UPDATE') for call in cursor.execute.call_args_list)


def test_failed_job_commit_does_not_acknowledge_pallet_intent():
    conn = MagicMock()
    conn.commit.side_effect = RuntimeError('DB commit failed')
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    with patch('app.utils.pallet_label.prepare_pallet_label_data', return_value={'nr_palety': 'test'}), \
         patch('app.repositories.settings_repository.SettingsRepository.get_default_printer_for_line',
               return_value={'ip': '192.0.2.1', 'nazwa': 'Audit'}), \
         patch('app.services.print_server.get_printer'):
        with pytest.raises(RuntimeError, match='DB commit failed'):
            AutoLabelService.queue_for_pallet(conn, cursor, 55)
    assert not any(call.args[0].lstrip().startswith('UPDATE') for call in cursor.execute.call_args_list)


def test_recovery_does_not_touch_registration_in_progress():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (0,)
    with patch('app.services.auto_label_service.get_db_connection', return_value=conn):
        assert AutoLabelService.recover_pending() == 0
    cursor.fetchall.assert_not_called()
    conn.close.assert_called_once()


@pytest.fixture(autouse=True)
def clear_schema_cache():
    AutoLabelService._schema_checks.clear()
    yield
    AutoLabelService._schema_checks.clear()


def test_missing_schema_is_checked_without_mutation_and_warning_is_not_repeated():
    conn, cursor = MagicMock(), MagicMock()
    conn.database = 'biblioteka_testowa'
    cursor.fetchone.return_value = None
    with patch('app.services.auto_label_service.time.monotonic', side_effect=[0, 1, 61]), \
         patch('app.services.auto_label_service.logger.warning') as warning:
        assert AutoLabelService.schema_ready(conn, cursor) is False
        assert AutoLabelService.schema_ready(conn, cursor) is False
        assert AutoLabelService.schema_ready(conn, cursor) is False
    assert cursor.execute.call_count == 2
    assert all(call.args[0].startswith('SHOW ') for call in cursor.execute.call_args_list)
    warning.assert_called_once()
    conn.commit.assert_not_called()


def test_schema_cache_does_not_leak_across_databases_and_recovers_after_migration():
    conn, cursor = MagicMock(), MagicMock()
    conn.database = 'biblioteka_testowa'
    cursor.fetchone.return_value = None
    with patch('app.services.auto_label_service.time.monotonic', side_effect=[0, 1, 61]):
        assert not AutoLabelService.schema_ready(conn, cursor)
        conn.database = 'biblioteka'
        cursor.fetchone.return_value = ('present',)
        assert AutoLabelService.schema_ready(conn, cursor)
        conn.database = 'biblioteka_testowa'
        assert AutoLabelService.schema_ready(conn, cursor)


@pytest.mark.parametrize('rows', [[None], [('column',), None], [('column',), ('column',), None]])
def test_incomplete_schema_never_starts_recovery(rows):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,)] + rows + [(1,)]
    with patch('app.services.auto_label_service.get_db_connection', return_value=conn), \
         patch.object(AutoLabelService, 'queue_for_pallet') as queue:
        assert AutoLabelService.recover_pending() == 0
    queue.assert_not_called()
    conn.commit.assert_not_called()
    cursor.fetchall.assert_not_called()
    assert not any("WHERE auto_label_state=" in call.args[0] for call in cursor.execute.call_args_list)
    conn.close.assert_called_once()


def test_complete_schema_recovers_existing_pending_ids():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,), ('column',), ('column',), ('unique_index',), (1,)]
    cursor.fetchall.return_value = [(12,), (13,)]
    with patch('app.services.auto_label_service.get_db_connection', return_value=conn), \
         patch.object(AutoLabelService, 'queue_for_pallet') as queue:
        assert AutoLabelService.recover_pending() == 2
    assert queue.call_count == 2
    conn.close.assert_called_once()


def test_metadata_connection_error_remains_visible_and_is_not_cached():
    from mysql.connector import Error
    conn, cursor = MagicMock(), MagicMock()
    cursor.execute.side_effect = Error('connection lost', errno=2013)
    with pytest.raises(Error):
        AutoLabelService.schema_ready(conn, cursor)
    assert not AutoLabelService._schema_checks


def test_missing_schema_blocks_registration_before_stock_or_plan_writes():
    from app.repositories.agro_tanks_repository import AgroTanksRepository
    conn = MagicMock()
    with patch('app.repositories.agro_tanks_repository.get_db_connection', return_value=conn), \
         patch.object(AutoLabelService, 'schema_ready', return_value=False):
        assert AgroTanksRepository.auto_register_pallet(322) is False
    statements = [call.args[0].lstrip().upper() for call in conn.cursor.return_value.execute.call_args_list]
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE', 'ALTER', 'CREATE')) for sql in statements)
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
