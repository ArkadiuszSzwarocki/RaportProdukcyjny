"""Production navigation reads stay bounded as orders and batches grow."""
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from app.services.zasyp_etapy_service import ZasypEtapyService
from app.services.shift_time_service import ShiftTimeService


def test_dashboard_batches_stage_reads_and_preserves_legacy_sessions():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    rows = [dict(plan_id=1, szarza_nr=n, etap=1, czas_start=datetime(2026, 10, 24, 7),
                 czas_stop=datetime(2026, 10, 24, 8), pauza_sekundy=120) for n in range(1, 51)]
    # Legacy NULL and zero batch IDs are rendered as batch 1.
    rows += [dict(plan_id=2, szarza_nr=None, etap=1), dict(plan_id=2, szarza_nr=0, etap=2)]
    cursor.fetchall.side_effect = [rows, [{'plan_id': 3, 'max_val': 7}], [{'plan_id': 1, 'wielkosc_szarzy_kg': 800}]]
    with patch('app.services.zasyp_etapy_service.get_db_connection', return_value=conn) as acquire:
        sessions, params = ZasypEtapyService.get_dashboard_sessions([1, 2, 3, 4], 'AGRO')
    acquire.assert_called_once()
    assert cursor.execute.call_count == 3
    assert all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list)
    assert [row['szarza_nr'] for row in sessions[1]] == list(range(50, 0, -1))
    assert sessions[1][0]['is_current'] and not sessions[1][1]['is_current']
    assert sessions[1][0]['total_duration_s'] == 3480
    assert all(row['exists'] for row in sessions[2][0]['etapy'][:2])
    assert sessions[3][0]['szarza_nr'] == 7
    assert sessions[4][0]['szarza_nr'] == 1
    assert params[1] == {'wielkosc_szarzy_kg': 800.0}
    assert params[4] == {'wielkosc_szarzy_kg': None}
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_dashboard_stage_read_releases_connection_on_failure():
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError('Read failed')
    with patch('app.services.zasyp_etapy_service.get_db_connection', return_value=conn):
        with pytest.raises(RuntimeError, match='Read failed'):
            ZasypEtapyService.get_dashboard_sessions([1], 'PSD')
    conn.cursor.return_value.close.assert_called_once()
    conn.close.assert_called_once()


def test_empty_stages_do_not_acquire_connection():
    with patch('app.services.zasyp_etapy_service.get_db_connection') as acquire:
        assert ZasypEtapyService.get_dashboard_sessions([], 'AGRO') == ({}, {})
    acquire.assert_not_called()


def test_productivity_reuses_same_shift_range_for_all_rows():
    with patch.object(ShiftTimeService, 'get_shift_time_range', side_effect=AssertionError('Repeated schedule read')):
        metrics = ShiftTimeService.calculate_productivity(1000, 60, '2026-10-24', shift_range=(480, '07:00', '15:00'))
    assert metrics['wydajnosc_rzeczywista'] == 125
    assert metrics['wydajnosc_efektywna'] == 142.9
    assert metrics['netto_min'] == 420


def test_reading_shift_schedule_never_changes_schema_or_commits():
    from app.services.auto_report.auto_report_schedule_service import AutoReportScheduleService
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'scheduled_time': '16:30', 'is_paused': False}
    with patch('app.services.auto_report.auto_report_schedule_service.get_db_connection', return_value=conn), patch('app.services.auto_report.auto_report_schedule_service.AutoReportHistoryService.ensure_history_tables', side_effect=AssertionError('Schema changes on GET')):
        result = AutoReportScheduleService.get_schedule('AGRO', '2026-10-24')
    assert result['scheduled_time'] == '16:30'
    assert conn.cursor.return_value.execute.call_count == 1
    assert conn.cursor.return_value.execute.call_args.args[0].lstrip().startswith('SELECT')
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_pool_size_limits_local_startup_without_changing_production_default(monkeypatch):
    from app.core import database
    monkeypatch.delenv('DB_POOL_SIZE', raising=False)
    monkeypatch.setattr(database, 'is_local', True)
    assert database._configured_pool_size() == 8
    monkeypatch.setattr(database, 'is_local', False)
    assert database._configured_pool_size() == 32
    monkeypatch.setenv('DB_POOL_SIZE', '4')
    assert database._configured_pool_size() == 4
    monkeypatch.setenv('DB_POOL_SIZE', '99')
    assert database._configured_pool_size() == 32
    monkeypatch.setenv('DB_POOL_SIZE', '0')
    assert database._configured_pool_size() == 1
    monkeypatch.setenv('DB_POOL_SIZE', 'bad')
    assert database._configured_pool_size() == 32
