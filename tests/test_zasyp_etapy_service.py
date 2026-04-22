from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.zasyp_etapy_service import ZasypEtapyService, _visible_etaps_for_linia


def test_agro_visible_etaps_skip_stage_3():
    assert _visible_etaps_for_linia('AGRO') == [1, 2, 4, 5, 6]


@patch('app.services.zasyp_etapy_service.get_db_connection')
def test_get_etapy_agro_ignores_stage_3(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    mock_cursor.fetchone.side_effect = [
        {'c': 1},
    ]
    mock_cursor.fetchall.return_value = [
        {'etap': 1, 'czas_start': datetime(2026, 4, 22, 8, 0), 'czas_stop': datetime(2026, 4, 22, 8, 5), 'start_login': 'a', 'stop_login': 'b'},
        {'etap': 2, 'czas_start': datetime(2026, 4, 22, 8, 5), 'czas_stop': datetime(2026, 4, 22, 8, 10), 'start_login': 'a', 'stop_login': 'b'},
        {'etap': 3, 'czas_start': datetime(2026, 4, 22, 8, 10), 'czas_stop': None, 'start_login': 'a', 'stop_login': None},
        {'etap': 4, 'czas_start': None, 'czas_stop': None, 'start_login': None, 'stop_login': None},
    ]

    result = ZasypEtapyService.get_etapy(plan_id=49, linia='AGRO')

    etap_numbers = [item['etap'] for item in result['etapy']]
    assert etap_numbers == [1, 2, 4, 5, 6]
    assert result['active_etap'] is None


@patch('app.services.zasyp_etapy_service.get_db_connection')
def test_start_etap_accepts_agro_stage_3(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    mock_cursor.fetchone.side_effect = [
        (1,),
        None,
        None,
    ]

    ok, msg = ZasypEtapyService.start_etap(plan_id=49, linia='AGRO', data_planu=datetime(2026, 4, 22).date(), etap=3, user_login='test')
    assert ok is False
    assert 'Nieprawidłowy etap' in msg


@patch('app.services.zasyp_etapy_service.get_db_connection')
def test_restart_completed_agro_stage_4(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    mock_cursor.fetchone.side_effect = [
        (1,),
        None,
        (datetime(2026, 4, 22, 8, 10), datetime(2026, 4, 22, 8, 15)),
    ]

    ok, msg = ZasypEtapyService.start_etap(plan_id=49, linia='AGRO', data_planu=datetime(2026, 4, 22).date(), etap=4, user_login='test')
    assert ok is True
    assert 'Start etapu 4 zapisany' in msg
