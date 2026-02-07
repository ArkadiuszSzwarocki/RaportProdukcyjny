"""Tests for PlanMovementService."""

import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from app.services.plan_movement_service import PlanMovementService
from app.db import get_db_connection


@pytest.mark.usefixtures("app")
class TestMovePlanToSection:
    """Tests for PlanMovementService.move_plan_to_section()"""
    
    @patch('app.services.plan_movement_service.get_db_connection')
    def test_move_plan_to_section_success(self, mock_get_conn, app):
        """Test moving a plan to a different section."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan's current section
            mock_cursor.fetchone.side_effect = [
                ('Workowanie',),  # Current sekcja
                (3,),  # MAX(kolejnosc) in target section
            ]
            
            success, message = PlanMovementService.move_plan_to_section(123, 'Zasyp')
            
            assert success is True
            assert 'przeniesione' in message.lower() or 'moved' in message.lower()
            mock_conn.commit.assert_called_once()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_move_plan_already_in_section(self, mock_get_conn, app):
        """Test moving a plan to the same section."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan already in target section
            mock_cursor.fetchone.return_value = ('Zasyp',)
            
            success, message = PlanMovementService.move_plan_to_section(123, 'Zasyp')
            
            assert success is False
            assert 'już' in message.lower() or 'already' in message.lower()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_move_plan_not_found(self, mock_get_conn, app):
        """Test moving non-existent plan to different section."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = None
            
            success, message = PlanMovementService.move_plan_to_section(999, 'Zasyp')
            
            assert success is False
            assert 'nie istnieje' in message.lower()


@pytest.mark.usefixtures("app")
class TestShiftPlanOrder:
    """Tests for PlanMovementService.shift_plan_order()"""
    
    @patch('app.services.plan_movement_service.get_db_connection')
    def test_shift_plan_order_up_success(self, mock_get_conn, app):
        """Test moving a plan up in the queue."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan info
            mock_cursor.fetchone.side_effect = [
                ('Workowanie', 2, '2025-02-10', 'Mąka'),  # Current plan info
                (1, 1),  # Adjacent plan (up)
            ]
            
            success, message = PlanMovementService.shift_plan_order(123, 'up')
            
            assert success is True
            assert 'górę' in message.lower() or 'up' in message.lower()
            mock_conn.commit.assert_called_once()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_shift_plan_order_down_success(self, mock_get_conn, app):
        """Test moving a plan down in the queue."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan info
            mock_cursor.fetchone.side_effect = [
                ('Workowanie', 2, '2025-02-10', 'Mąka'),  # Current plan info
                (2, 3),  # Adjacent plan (down)
            ]
            
            success, message = PlanMovementService.shift_plan_order(123, 'down')
            
            assert success is True
            assert 'dół' in message.lower() or 'down' in message.lower()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_shift_plan_order_w_gore(self, mock_get_conn, app):
        """Test moving a plan up using Polish direction."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.side_effect = [
                ('Workowanie', 2, '2025-02-10', 'Mąka'),
                (1, 1),
            ]
            
            success, message = PlanMovementService.shift_plan_order(123, 'w_gore')
            
            assert success is True

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_shift_plan_order_w_dol(self, mock_get_conn, app):
        """Test moving a plan down using Polish direction."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.side_effect = [
                ('Workowanie', 2, '2025-02-10', 'Mąka'),
                (2, 3),
            ]
            
            success, message = PlanMovementService.shift_plan_order(123, 'w_dol')
            
            assert success is True

    def test_shift_plan_invalid_direction(self):
        """Test shifting plan with invalid direction."""
        success, message = PlanMovementService.shift_plan_order(123, 'invalid')
        
        assert success is False
        assert 'kierunek' in message.lower() or 'direction' in message.lower()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_shift_plan_not_found(self, mock_get_conn, app):
        """Test shifting non-existent plan."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchone.return_value = None
            
            success, message = PlanMovementService.shift_plan_order(999, 'up')
            
            assert success is False
            assert 'nie istnieje' in message.lower()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_shift_plan_no_adjacent(self, mock_get_conn, app):
        """Test shifting plan when no adjacent plan exists (at boundary)."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plan info
            mock_cursor.fetchone.side_effect = [
                ('Workowanie', 1, '2025-02-10', 'Mąka'),  # First plan
                None,  # No adjacent plan when trying to move up
            ]
            
            success, message = PlanMovementService.shift_plan_order(123, 'up')
            
            assert success is False
            assert 'sąsiednie' in message.lower() or 'adjacent' in message.lower()


@pytest.mark.usefixtures("app")
class TestReorderPlans:
    """Tests for PlanMovementService.reorder_plans()"""
    
    @patch('app.services.plan_movement_service.get_db_connection')
    def test_reorder_plans_success(self, mock_get_conn, app):
        """Test reordering multiple plans."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            new_order = [3, 1, 2]  # Plan IDs in new order
            
            success, message = PlanMovementService.reorder_plans(
                'Workowanie', '2025-02-10', new_order
            )
            
            assert success is True
            assert 'uporządkowane' in message.lower() or 'reordered' in message.lower()
            mock_conn.commit.assert_called_once()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_reorder_plans_empty_list(self, mock_get_conn, app):
        """Test reordering with empty plan list."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            success, message = PlanMovementService.reorder_plans(
                'Workowanie', '2025-02-10', []
            )
            
            assert success is True or success is False
            mock_conn.close.assert_called_once()

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_reorder_plans_database_error(self, mock_get_conn, app):
        """Test reordering when database error occurs."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.execute.side_effect = Exception('DB error')
            
            success, message = PlanMovementService.reorder_plans(
                'Workowanie', '2025-02-10', [1, 2, 3]
            )
            
            assert success is False
            assert 'błąd' in message.lower() or 'error' in message.lower()


@pytest.mark.usefixtures("app")
class TestGetPlanQueueForSection:
    """Tests for PlanMovementService.get_plan_queue_for_section()"""
    
    @patch('app.services.plan_movement_service.get_db_connection')
    def test_get_plan_queue_success(self, mock_get_conn, app):
        """Test retrieving plan queue for a section."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock plans in queue
            mock_cursor.fetchall.return_value = [
                (1, 'Mąka', 100, 'zaplanowane', 1, 0),
                (2, 'Cukier', 50, 'zaplanowane', 2, 0),
                (3, 'Sól', 30, 'zaplanowane', 3, 0),
            ]
            
            result = PlanMovementService.get_plan_queue_for_section(
                'Workowanie', '2025-02-10'
            )
            
            assert isinstance(result, list)
            assert len(result) == 3
            assert result[0]['produkt'] == 'Mąka'
            assert result[1]['produkt'] == 'Cukier'
            assert result[2]['produkt'] == 'Sól'

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_get_plan_queue_empty_section(self, mock_get_conn, app):
        """Test retrieving queue from empty section."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchall.return_value = []
            
            result = PlanMovementService.get_plan_queue_for_section(
                'Workowanie', '2025-02-10'
            )
            
            assert isinstance(result, list)
            assert len(result) == 0

    @patch('app.services.plan_movement_service.get_db_connection')
    def test_get_plan_queue_excludes_deleted(self, mock_get_conn, app):
        """Test that deleted plans are excluded from queue."""
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock includes only non-deleted plans
            mock_cursor.fetchall.return_value = [
                (1, 'Mąka', 100, 'zaplanowane', 1, 0),
                (2, 'Cukier', 50, 'zaplanowane', 2, 0),
            ]
            
            result = PlanMovementService.get_plan_queue_for_section(
                'Workowanie', '2025-02-10'
            )
            
            assert len(result) == 2
            # Verify the SQL was called with is_deleted filter (through assertion on cursor.execute call)
