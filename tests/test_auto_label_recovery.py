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
