"""Integration-style test for przenies_niezrealizowane (service-level, no HTTP)."""

import pytest
from unittest.mock import MagicMock, patch

from app.services.planning_service import PlanningService


@pytest.mark.usefixtures("app")
def test_przenies_niezrealizowane_creates_carryover(app, monkeypatch):
    """Call przenies_niezrealizowane and ensure it creates carryover plans when Workowanie has remaining."""
    # Mock DB connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # One plan returned: has workowanie and remaining = 30
    mock_cursor.fetchall.return_value = [
        {
            'zasyp_id': 1,
            'produkt': 'TESTPROD',
            'typ_produkcji': None,
            'z_plan': 100,
            'z_real': 100,
            'workowanie_id': 10,
            'w_plan': 50,
            'w_real': 20,
        }
    ]

    # First fetchone() for duplicate check -> None, then for max kolejka -> (0,)
    mock_cursor.fetchone.side_effect = [None, (0,)]

    with patch('app.services.planning_service.get_db_connection', return_value=mock_conn):
        with app.app_context():
            # Patch create_plan to simulate successful insert with id (only Workowanie created)
            with patch('app.services.planning_service.PlanningService.create_plan') as mock_create:
                mock_create.side_effect = [ (True, 'ok', 111) ]

                success, message, count = PlanningService.przenies_niezrealizowane('2026-03-27')

                assert success is True
                assert isinstance(message, str)
                # One Workowanie plan created
                assert count == 1