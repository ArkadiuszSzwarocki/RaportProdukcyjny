from unittest.mock import Mock

import pytest

from app.services.scanner_sync_service import ScannerSyncService


@pytest.mark.parametrize('action', ['RELOCATE', 'VERIFY', 'RECEIVE', 'CANCEL'])
def test_stock_actions_are_never_acknowledged_as_lookups(monkeypatch, action):
    seen = Mock()
    lookup = Mock()
    record = Mock()
    monkeypatch.setattr(ScannerSyncService, 'is_event_already_processed', seen)
    monkeypatch.setattr('app.services.scanner_sync_service.ScannerService.lookup_scanned_code', lookup)
    monkeypatch.setattr(ScannerSyncService, 'record_synced_event', record)
    result = ScannerSyncService.process_sync_batch([
        {'client_uuid': 'one', 'scanned_code': 'PAL-15', 'scan_action': action},
    ], user_login='operator')
    assert result['processed'] == 0
    assert result['items'][0]['status'] == 'INVALID'
    seen.assert_not_called()
    lookup.assert_not_called()
    record.assert_not_called()


@pytest.mark.parametrize('field,value', [('client_uuid', 'x' * 101), ('scanned_code', 'x' * 256)])
def test_oversized_scan_does_not_break_other_batch_events(monkeypatch, field, value):
    seen = Mock(return_value=False)
    record = Mock()
    monkeypatch.setattr(ScannerSyncService, 'is_event_already_processed', seen)
    monkeypatch.setattr('app.services.scanner_sync_service.ScannerService.lookup_scanned_code', Mock(return_value={'success': True}))
    monkeypatch.setattr(ScannerSyncService, 'record_synced_event', record)
    invalid = {'client_uuid': 'one', 'scanned_code': 'PAL-15', field: value}
    result = ScannerSyncService.process_sync_batch([
        invalid, {'client_uuid': 'two', 'scanned_code': 'PAL-16'},
    ], user_login='operator')
    assert [item['status'] for item in result['items']] == ['INVALID', 'SUCCESS']
    assert result['processed'] == 1
    record.assert_called_once()
    assert record.call_args.kwargs['scan_action'] == 'LOOKUP'
