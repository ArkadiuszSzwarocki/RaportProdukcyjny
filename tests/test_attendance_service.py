"""Tests for AttendanceService."""

import pytest
import sys
import os
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import Flask app directly from app.py module
import importlib.util
spec = importlib.util.spec_from_file_location("app_module", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py"))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
flask_app = app_module.app

from app.services.attendance_service import AttendanceService


@pytest.fixture
def app_context():
    """Provide Flask app context for testing."""
    with flask_app.app_context():
        yield flask_app


class TestAddToSchedule:
    """Tests for AttendanceService.add_to_schedule()"""

    def test_add_to_schedule_success(self, app_context):
        """Test successful addition to schedule."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            cursor_mock.fetchone.side_effect = [
                (1,),  # inserted id
                ('Jan Kowalski',)  # employee name
            ]
            
            success, inserted_id, name = AttendanceService.add_to_schedule(
                sekcja='Zasyp',
                pracownik_id=1,
                date_str='2026-02-07'
            )
            
            assert success is True
            assert inserted_id == 1
            assert name == 'Jan Kowalski'

    def test_add_to_schedule_no_date(self, app_context):
        """Test addition to schedule with today's date by default."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            cursor_mock.fetchone.side_effect = [
                (2,),
                ('Anna Nowak',)
            ]
            
            success, inserted_id, name = AttendanceService.add_to_schedule(
                sekcja='Workowanie',
                pracownik_id=2,
                date_str=None
            )
            
            assert success is True

    def test_add_to_schedule_invalid_date(self, app_context):
        """Test addition with invalid date format."""
        success, inserted_id, name = AttendanceService.add_to_schedule(
            sekcja='Zasyp',
            pracownik_id=1,
            date_str='invalid-date'
        )
        
        assert success is False

    def test_add_to_schedule_error(self, app_context):
        """Test addition handles database errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            success, inserted_id, name = AttendanceService.add_to_schedule(
                sekcja='Zasyp',
                pracownik_id=1,
                date_str='2026-02-07'
            )
            
            assert success is False


class TestRemoveFromSchedule:
    """Tests for AttendanceService.remove_from_schedule()"""

    def test_remove_from_schedule_success(self, app_context):
        """Test successful removal from schedule."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            cursor_mock.fetchone.return_value = (1, date(2026, 2, 7), 'Zasyp')
            
            success = AttendanceService.remove_from_schedule(1)
            
            assert success is True

    def test_remove_from_schedule_nonexistent(self, app_context):
        """Test removal of nonexistent schedule record."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            cursor_mock.fetchone.return_value = None
            
            success = AttendanceService.remove_from_schedule(999)
            
            # Should still return True (graceful handling)
            assert success is True

    def test_remove_from_schedule_error(self, app_context):
        """Test removal handles database errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            success = AttendanceService.remove_from_schedule(1)
            
            assert success is False


class TestSaveShiftLeaders:
    """Tests for AttendanceService.save_shift_leaders()"""

    def test_save_shift_leaders_success(self, app_context):
        """Test successful saving of shift leaders."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            success = AttendanceService.save_shift_leaders(
                date_str='2026-02-07',
                lider_psd_id=1,
                lider_agro_id=2
            )
            
            assert success is True

    def test_save_shift_leaders_none_values(self, app_context):
        """Test saving shift leaders with None values."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            success = AttendanceService.save_shift_leaders(
                date_str='2026-02-07',
                lider_psd_id=None,
                lider_agro_id=None
            )
            
            assert success is True

    def test_save_shift_leaders_invalid_date(self, app_context):
        """Test saving with invalid date format."""
        success = AttendanceService.save_shift_leaders(
            date_str='invalid-date',
            lider_psd_id=1,
            lider_agro_id=2
        )
        
        assert success is False

    def test_save_shift_leaders_error(self, app_context):
        """Test saving handles database errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            success = AttendanceService.save_shift_leaders(
                date_str='2026-02-07',
                lider_psd_id=1,
                lider_agro_id=2
            )
            
            assert success is False


class TestDeleteAbsenceRecord:
    """Tests for AttendanceService.delete_absence_record()"""

    def test_delete_absence_record_success(self, app_context):
        """Test successful deletion of absence record."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            cursor_mock = MagicMock()
            conn_mock = MagicMock()
            mock_conn.return_value = conn_mock
            conn_mock.cursor.return_value = cursor_mock
            
            success = AttendanceService.delete_absence_record(1)
            
            assert success is True

    def test_delete_absence_record_error(self, app_context):
        """Test deletion handles database errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            mock_conn.return_value.cursor.side_effect = Exception('DB Error')
            
            success = AttendanceService.delete_absence_record(1)
            
            assert success is False


class TestGetPendingRequestsPanel:
    """Tests for AttendanceService.get_pending_requests_panel()"""

    def test_get_pending_requests_panel_success(self, app_context):
        """Test retrieving pending requests panel."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                cursor_mock = MagicMock()
                conn_mock = MagicMock()
                mock_conn.return_value = conn_mock
                conn_mock.cursor.return_value = cursor_mock
                
                cursor_mock.fetchall.return_value = [
                    (1, 'Jan Kowalski', 'Urlop', date(2026, 2, 10), date(2026, 2, 14), None, None, 'Test', datetime(2026, 2, 1))
                ]
                mock_render.return_value = '<div>Pending Requests</div>'
                
                result = AttendanceService.get_pending_requests_panel()
                
                assert '<div' in result

    def test_get_pending_requests_panel_no_requests(self, app_context):
        """Test pending requests panel with no requests."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                cursor_mock = MagicMock()
                conn_mock = MagicMock()
                mock_conn.return_value = conn_mock
                conn_mock.cursor.return_value = cursor_mock
                
                cursor_mock.fetchall.return_value = []
                mock_render.return_value = '<div>No Requests</div>'
                
                result = AttendanceService.get_pending_requests_panel()
                
                assert 'No Requests' in result or result

    def test_get_pending_requests_panel_error(self, app_context):
        """Test pending requests panel handles errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                mock_conn.return_value.cursor.side_effect = Exception('DB Error')
                mock_render.return_value = '<div>Error</div>'
                
                result = AttendanceService.get_pending_requests_panel()
                
                # Should return rendered template even on error
                assert result


class TestGetPlannedLeavesPanel:
    """Tests for AttendanceService.get_planned_leaves_panel()"""

    def test_get_planned_leaves_panel_success(self, app_context):
        """Test retrieving planned leaves panel."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                cursor_mock = MagicMock()
                conn_mock = MagicMock()
                mock_conn.return_value = conn_mock
                conn_mock.cursor.return_value = cursor_mock
                
                cursor_mock.fetchall.return_value = [
                    (1, 'Jan Kowalski', 'Urlop', date(2026, 2, 10), date(2026, 2, 14), None, None, 'approved')
                ]
                mock_render.return_value = '<div>Planned Leaves</div>'
                
                result = AttendanceService.get_planned_leaves_panel()
                
                assert 'Planned' in result or result

    def test_get_planned_leaves_panel_error(self, app_context):
        """Test planned leaves panel handles errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                mock_conn.return_value.cursor.side_effect = Exception('DB Error')
                mock_render.return_value = '<div>Error</div>'
                
                result = AttendanceService.get_planned_leaves_panel()
                
                assert result


class TestGetRecentAbsencesPanel:
    """Tests for AttendanceService.get_recent_absences_panel()"""

    def test_get_recent_absences_panel_success(self, app_context):
        """Test retrieving recent absences panel."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                cursor_mock = MagicMock()
                conn_mock = MagicMock()
                mock_conn.return_value = conn_mock
                conn_mock.cursor.return_value = cursor_mock
                
                cursor_mock.fetchall.return_value = [
                    (1, 'Jan Kowalski', 'Nieobecność', date(2026, 1, 15), 8, 'Choroba')
                ]
                mock_render.return_value = '<div>Recent Absences</div>'
                
                result = AttendanceService.get_recent_absences_panel()
                
                assert result

    def test_get_recent_absences_panel_no_data(self, app_context):
        """Test recent absences panel with no data."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                cursor_mock = MagicMock()
                conn_mock = MagicMock()
                mock_conn.return_value = conn_mock
                conn_mock.cursor.return_value = cursor_mock
                
                cursor_mock.fetchall.return_value = []
                mock_render.return_value = '<div>No Absences</div>'
                
                result = AttendanceService.get_recent_absences_panel()
                
                assert result

    def test_get_recent_absences_panel_error(self, app_context):
        """Test recent absences panel handles errors gracefully."""
        with patch('app.services.attendance_service.get_db_connection') as mock_conn:
            with patch('app.services.attendance_service.render_template') as mock_render:
                mock_conn.return_value.cursor.side_effect = Exception('DB Error')
                mock_render.return_value = '<div>Error</div>'
                
                result = AttendanceService.get_recent_absences_panel()
                
                assert result
