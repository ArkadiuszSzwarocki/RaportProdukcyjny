"""Tests for PlanningService."""

import pytest
import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call

from app.services.planning_service import PlanningService
from app.db import get_db_connection


@pytest.mark.usefixtures("app")
class TestCreatePlan:
    """Tests for PlanningService.create_plan()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_create_plan_success(self, mock_get_conn, app):
        """Test creating a plan successfully."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock the sequence query
            mock_cursor.execute.side_effect = [
                MagicMock(),  # First call for MAX(kolejnosc)
                MagicMock(),  # Second call for INSERT
            ]
            mock_cursor.fetchone.return_value = (5,)  # Current max sequence
            
            success, message, plan_id = PlanningService.create_plan(
                data_planu='2025-02-10',
                produkt='Mąka',
                tonaz=100,
                sekcja='Workowanie',
                typ_produkcji='worki_25kg'
            )
            
            assert success is True
            assert 'Zlecenie' in message or 'plan' in message.lower()
            assert plan_id is not None
            mock_conn.commit.assert_called_once()
            mock_conn.close.assert_called_once()

    def test_create_plan_missing_produkt(self):
        """Test creating a plan without required product field."""
        success, message, plan_id = PlanningService.create_plan(
            data_planu='2025-02-10',
            produkt=None,  # Missing
            tonaz=100,
            sekcja='Workowanie'
        )
        
        assert success is False
        assert 'produkt' in message.lower()
        assert plan_id is None

    @patch('app.services.planning_service.get_db_connection')
    def test_create_plan_with_payment_flag(self, mock_get_conn, app):
        """Test creating a plan that requires payment."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = (0,)
            
            success, message, plan_id = PlanningService.create_plan(
                data_planu='2025-02-10',
                produkt='Mąka',
                tonaz=100,
                sekcja='Workowanie',
                wymaga_oplaty=True  # Flag set
            )
            
            assert success is True
            mock_conn.commit.assert_called_once()


@pytest.mark.usefixtures("app")
class TestDeletePlan:
    """Tests for PlanningService.delete_plan()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_delete_plan_success(self, mock_get_conn, app):
        """Test soft-deleting a plan successfully."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan exists with 'zaplanowane' status
            mock_cursor.fetchone.return_value = ('zaplanowane',)
            
            success, message = PlanningService.delete_plan(123)
            
            assert success is True
            assert 'usunięte' in message.lower() or 'deleted' in message.lower()
            mock_conn.commit.assert_called_once()
            mock_conn.close.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_delete_plan_not_found(self, mock_get_conn, app):
        """Test deleting non-existent plan."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = None  # Plan not found
            
            success, message = PlanningService.delete_plan(999)
            
            assert success is False
            assert 'nie istnieje' in message.lower()

    @patch('app.services.planning_service.get_db_connection')
    def test_delete_plan_in_progress(self, mock_get_conn, app):
        """Test deleting a plan that is in progress."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = ('w toku',)  # Status: in progress
            
            success, message = PlanningService.delete_plan(123)
            
            assert success is False
            assert 'w toku' in message.lower() or 'progress' in message.lower()

    @patch('app.services.planning_service.get_db_connection')
    def test_delete_plan_completed(self, mock_get_conn, app):
        """Test deleting a plan that is completed."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = ('zakonczone',)  # Status: completed
            
            success, message = PlanningService.delete_plan(123)
            
            assert success is False
            assert 'zakonczone' in message.lower() or 'completed' in message.lower()

    @patch('app.services.planning_service.get_db_connection')
    def test_delete_zasyp_cascades_workowanie(self, mock_get_conn, app):
        """Test: usunięcie Zasyp kaskadowo kasuje powiązane Workowanie (zasyp_id)."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # Zwraca (status, produkt, sekcja) = zaplanowane Zasyp
            mock_cursor.fetchone.return_value = ('zaplanowane', 'POLMLEK 100 %', 'Zasyp')
            mock_cursor.rowcount = 1  # jeden rekord Workowanie do usunięcia

            success, message = PlanningService.delete_plan(1215)

            assert success is True
            # Sprawdź, że wywołano kaskadowy DELETE dla Workowanie
            execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
            cascade_call = any("zasyp_id" in c for c in execute_calls)
            assert cascade_call, "Oczekiwano DELETE ... WHERE zasyp_id=%s dla kasowania powiązanego Workowanie"
            mock_conn.commit.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_delete_non_zasyp_no_cascade(self, mock_get_conn, app):
        """Test: usunięcie sekcji innej niż Zasyp NIE wykonuje kaskady Workowanie."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # Workowanie plan — nie powinno kaskadować
            mock_cursor.fetchone.return_value = ('zaplanowane', 'POLMLEK 100 %', 'Workowanie')

            success, message = PlanningService.delete_plan(1216)

            assert success is True
            execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
            cascade_call = any("zasyp_id" in c for c in execute_calls)
            assert not cascade_call, "Nie powinno być kaskadowego DELETE dla sekcji innej niż Zasyp"


@pytest.mark.usefixtures("app")
class TestRestorePlan:
    """Tests for PlanningService.restore_plan()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_restore_plan_success(self, mock_get_conn, app):
        """Test restoring a deleted plan."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = (1,)  # is_deleted=1
            
            success, message = PlanningService.restore_plan(123)
            
            assert success is True
            assert 'przywrócone' in message.lower() or 'restored' in message.lower()
            mock_conn.commit.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_restore_plan_not_deleted(self, mock_get_conn, app):
        """Test restoring a plan that was not deleted."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = (0,)  # is_deleted=0
            
            success, message = PlanningService.restore_plan(123)
            
            assert success is False
            assert 'nie' in message.lower()  # Should indicate failure


@pytest.mark.usefixtures("app")
class TestResumePlan:
    """Tests for PlanningService.resume_plan()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_resume_plan_success(self, mock_get_conn, app):
        """Test resuming a plan (changing to 'w toku')."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock getting plan's section
            mock_cursor.fetchone.return_value = ('Workowanie',)
            
            success, message = PlanningService.resume_plan(123)
            
            assert success is True
            assert 'w toku' in message.lower() or 'resumed' in message.lower()
            mock_conn.commit.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_resume_plan_not_found(self, mock_get_conn, app):
        """Test resuming non-existent plan."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = None  # Plan not found
            
            success, message = PlanningService.resume_plan(999)
            
            assert success is False
            assert 'nie istnieje' in message.lower()


@pytest.mark.usefixtures("app")
class TestChangeStatus:
    """Tests for PlanningService.change_status()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_change_status_success(self, mock_get_conn, app):
        """Test changing plan status."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            success, message = PlanningService.change_status(123, 'zakonczone')
            
            assert success is True
            mock_conn.commit.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_change_status_database_error(self, mock_get_conn, app):
        """Test changing status when database error occurs."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock exception
            mock_cursor.execute.side_effect = Exception('DB error')
            
            success, message = PlanningService.change_status(123, 'zakonczone')
            
            assert success is False
            assert 'błąd' in message.lower() or 'error' in message.lower()


@pytest.mark.usefixtures("app")
class TestGetPlanDetails:
    """Tests for PlanningService.get_plan_details()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_get_plan_details_success(self, mock_get_conn, app):
        """Test retrieving plan details."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan row
            mock_cursor.fetchone.return_value = (
                123, '2025-02-10', 'Mąka', 100, 'zaplanowane', 'Workowanie', 1, 'worki_25kg', 0, 0
            )
            
            result = PlanningService.get_plan_details(123)
            
            assert isinstance(result, dict)
            assert result['id'] == 123
            assert result['produkt'] == 'Mąka'
            assert result['status'] == 'zaplanowane'
            mock_conn.close.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_get_plan_details_not_found(self, mock_get_conn, app):
        """Test retrieving details of non-existent plan."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = None
            
            result = PlanningService.get_plan_details(999)
            
            assert isinstance(result, dict)
            assert 'error' in result


@pytest.mark.usefixtures("app")
class TestGetPlansForDate:
    """Tests for PlanningService.get_plans_for_date()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_get_plans_for_date_success(self, mock_get_conn, app):
        """Test retrieving plans for a specific date."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plans for date
            mock_cursor.fetchall.return_value = [
                (1, 'Mąka', 100, 'zaplanowane', 'Workowanie', 1, 'worki_25kg', 0),
                (2, 'Cukier', 50, 'w toku', 'Packowanie', 2, 'opakowania_1kg', 0),
            ]
            
            result = PlanningService.get_plans_for_date('2025-02-10')
            
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]['produkt'] == 'Mąka'
            assert result[1]['produkt'] == 'Cukier'
            mock_conn.close.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_get_plans_for_date_empty(self, mock_get_conn, app):
        """Test retrieving plans for date with no plans."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchall.return_value = []
            
            result = PlanningService.get_plans_for_date('2025-02-10')
            
            assert isinstance(result, list)
            assert len(result) == 0

    @patch('app.services.planning_service.get_db_connection')
    def test_get_plans_exclude_deleted(self, mock_get_conn, app):
        """Test retrieving plans excluding deleted ones."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchall.return_value = [
                (1, 'Mąka', 100, 'zaplanowane', 'Workowanie', 1, 'worki_25kg', 0),
            ]
            
            result = PlanningService.get_plans_for_date('2025-02-10', include_deleted=False)
            
            assert isinstance(result, list)
            assert len(result) == 1


@pytest.mark.usefixtures("app")
class TestReschedulePlan:
    """Tests for PlanningService.reschedule_plan()"""
    
    @patch('app.services.planning_service.get_db_connection')
    def test_reschedule_plan_success(self, mock_get_conn, app):
        """Test rescheduling a plan to a different date."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan exists with 'zaplanowane' status
            mock_cursor.fetchone.side_effect = [
                ('zaplanowane',),  # Status check
                (3,),  # MAX(kolejnosc) for new date
            ]
            
            success, message = PlanningService.reschedule_plan(123, '2025-02-15')
            
            assert success is True
            assert 'data' in message.lower() or 'przesunięte' in message.lower()
            mock_conn.commit.assert_called_once()

    @patch('app.services.planning_service.get_db_connection')
    def test_reschedule_plan_in_progress(self, mock_get_conn, app):
        """Test rescheduling a plan that is in progress."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = ('w toku',)
            
            success, message = PlanningService.reschedule_plan(123, '2025-02-15')
            
            assert success is False
            assert 'w toku' in message.lower()

    @patch('app.services.planning_service.get_db_connection')
    def test_reschedule_plan_not_found(self, mock_get_conn, app):
        """Test rescheduling non-existent plan."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = None
            
            success, message = PlanningService.reschedule_plan(999, '2025-02-15')
            
            assert success is False
            assert 'nie istnieje' in message.lower()
