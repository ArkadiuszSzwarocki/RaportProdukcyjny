"""Tests for LeaveRequestService."""

import pytest
import sys
import os
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch, call

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import Flask app directly from app.py module
import importlib.util
spec = importlib.util.spec_from_file_location("app_module", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py"))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
flask_app = app_module.app

from app.services.leave_request_service import LeaveRequestService


@pytest.fixture
def app_context():
    """Provide Flask app context for testing."""
    with flask_app.app_context():
        yield flask_app


class TestSubmitLeaveRequest:
    """Tests for LeaveRequestService.submit_leave_request()"""

    def test_submit_leave_request_success(self, app_context):
        """Test successful leave request submission."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            cursor_mock.lastrowid = 1
            
            success, message, request_id = LeaveRequestService.submit_leave_request(
                pracownik_id=1,
                typ='Urlop',
                data_od=date(2026, 2, 10),
                data_do=date(2026, 2, 14),
                czas_od=None,
                czas_do=None,
                powod='Zaplanowany urlop'
            )
            
            assert success is True
            assert 'pomyślnie' in message.lower()
            assert request_id == 1

    def test_submit_leave_request_single_day(self, app_context):
        """Test leave request submission for single day (Wyjście prywatne)."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            cursor_mock.lastrowid = 2
            
            success, message, request_id = LeaveRequestService.submit_leave_request(
                pracownik_id=1,
                typ='Wyjście prywatne',
                data_od=date(2026, 2, 10),
                data_do=None,  # Should be handled
                czas_od='14:00',
                czas_do='16:00',
                powod='Wizyta u lekarza'
            )
            
            assert success is True
            assert request_id == 2

    def test_submit_leave_request_missing_dates(self, app_context):
        """Test leave request fails with missing dates."""
        success, message, request_id = LeaveRequestService.submit_leave_request(
            pracownik_id=1,
            typ='Urlop',
            data_od=None,
            data_do=None,
            czas_od=None,
            czas_do=None,
            powod=''
        )
        
        assert success is False
        assert 'data' in message.lower()

    def test_submit_leave_request_range_dates_required(self, app_context):
        """Test that regular leave requires date range."""
        success, message, request_id = LeaveRequestService.submit_leave_request(
            pracownik_id=1,
            typ='Urlop',
            data_od=date(2026, 2, 10),
            data_do=None,
            czas_od=None,
            czas_do=None,
            powod='Test'
        )
        
        assert success is False
        assert 'zakres' in message.lower() or 'data_do' in message.lower()


class TestApproveLeaveRequest:
    """Tests for LeaveRequestService.approve_leave_request()"""

    def test_approve_leave_request_success(self, app_context):
        """Test successful leave request approval with counter update."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            
            # Mock first query to get request details
            cursor_mock.fetchone.side_effect = [
                (1, date(2026, 2, 10), date(2026, 2, 14), 'Urlop'),
            ]
            
            success, message = LeaveRequestService.approve_leave_request(1, 5)
            
            assert success is True
            assert 'zatwierdzony' in message.lower() or 'approved' in message.lower()

    def test_approve_leave_request_with_zalegly_counter(self, app_context):
        """Test approval with urlop_zalegly counter update."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            
            cursor_mock.fetchone.side_effect = [
                (2, date(2026, 2, 10), date(2026, 2, 14), 'Urlop zaległy'),
            ]
            
            success, message = LeaveRequestService.approve_leave_request(2, 5)
            
            assert success is True

    def test_approve_leave_request_error(self, app_context):
        """Test approval handles database errors gracefully."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            success, message = LeaveRequestService.approve_leave_request(999, 5)
            
            assert success is False
            assert 'błąd' in message.lower() or 'error' in message.lower()


class TestRejectLeaveRequest:
    """Tests for LeaveRequestService.reject_leave_request()"""

    def test_reject_leave_request_success(self, app_context):
        """Test successful leave request rejection."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            
            success, message = LeaveRequestService.reject_leave_request(1, 5)
            
            assert success is True
            assert 'odrzuc' in message.lower()

    def test_reject_leave_request_error(self, app_context):
        """Test rejection handles database errors gracefully."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            success, message = LeaveRequestService.reject_leave_request(999, 5)
            
            assert success is False


class TestGetRequestsForDay:
    """Tests for LeaveRequestService.get_requests_for_day()"""

    def test_get_requests_for_day_success(self, app_context):
        """Test retrieving leave requests for a specific day."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            
            cursor_mock.fetchall.return_value = [
                (1, 'Urlop', date(2026, 2, 10), date(2026, 2, 14), None, None, 'Urlop', 'pending', datetime(2026, 2, 1))
            ]
            
            result = LeaveRequestService.get_requests_for_day(1, '2026-02-12')
            
            assert 'wnioski' in result
            assert isinstance(result['wnioski'], list)
            assert len(result['wnioski']) > 0

    def test_get_requests_for_day_no_requests(self, app_context):
        """Test retrieving leave requests when none exist."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            cursor_mock.fetchall.return_value = []
            
            result = LeaveRequestService.get_requests_for_day(1, '2026-02-12')
            
            assert 'wnioski' in result
            assert result['wnioski'] == []

    def test_get_requests_for_day_error(self, app_context):
        """Test error handling when querying fails."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            result = LeaveRequestService.get_requests_for_day(1, '2026-02-12')
            
            assert 'error' in result


class TestGetSummaryForEmployee:
    """Tests for LeaveRequestService.get_summary_for_employee()"""

    def test_get_summary_for_employee_success(self, app_context):
        """Test retrieving summary for employee."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            
            # Mock multiple queries
            cursor_mock.fetchone.side_effect = [
                (5,),  # obecnosci count
                (10,),  # urlop_biezacy
                (2,),   # urlop_zalegly
            ]
            cursor_mock.fetchall.side_effect = [
                [('Obecność', 40.0)],  # typy
                [(3600.0,)],  # wyjscia_hours
            ]
            
            result = LeaveRequestService.get_summary_for_employee(1)
            
            assert 'obecnosci' in result
            assert 'typy' in result
            assert 'urlop_biezacy' in result
            assert 'urlop_zalegly' in result

    def test_get_summary_for_employee_no_data(self, app_context):
        """Test summary with missing employee data."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            mock_conn.return_value.cursor.return_value = cursor_mock
            cursor_mock.fetchone.return_value = None
            cursor_mock.fetchall.return_value = []
            
            result = LeaveRequestService.get_summary_for_employee(999)
            
            # Should have default values, not error
            assert 'obecnosci' in result or 'error' not in result

    def test_get_summary_for_employee_error(self, app_context):
        """Test error handling when retrieving summary fails."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            result = LeaveRequestService.get_summary_for_employee(1)
            
            assert 'error' in result


class TestUpdateLeaveCounters:
    """Tests for LeaveRequestService._update_leave_counters()"""

    def test_update_leave_counters_urlop_biezacy(self, app_context):
        """Test updating current year leave counter."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            # This is a private method, test indirectly via approve_leave_request
            # which calls _update_leave_counters
            cursor_mock.fetchone.side_effect = [
                (1, date(2026, 2, 10), date(2026, 2, 14), 'Urlop'),
            ]
            
            LeaveRequestService.approve_leave_request(1, 5)
            
            # Verify UPDATE was called
            assert cursor_mock.execute.called

    def test_update_leave_counters_urlop_zalegly(self, app_context):
        """Test updating carryover leave counter."""
        with patch('app.services.leave_request_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            cursor_mock.fetchone.side_effect = [
                (1, date(2026, 2, 10), date(2026, 2, 14), 'Urlop zaległy 2025'),
            ]
            
            LeaveRequestService.approve_leave_request(1, 5)
            
            assert cursor_mock.execute.called
