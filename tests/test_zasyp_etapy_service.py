from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.zasyp_etapy_service import ZasypEtapyService, _visible_etaps_for_linia


def test_agro_visible_etaps_sequence_1_to_5():
    assert _visible_etaps_for_linia('AGRO') == [1, 2, 3, 4, 5]


@patch('app.services.zasyp_etapy_service.get_db_connection')
def test_get_etapy_agro_includes_stage_3(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    mock_cursor.fetchone.side_effect = [
        (1,),
    ]
    mock_cursor.fetchall.return_value = [
        {'etap': 1, 'czas_start': datetime(2026, 4, 22, 8, 0), 'czas_stop': datetime(2026, 4, 22, 8, 5), 'start_login': 'a', 'stop_login': 'b'},
        {'etap': 2, 'czas_start': datetime(2026, 4, 22, 8, 5), 'czas_stop': datetime(2026, 4, 22, 8, 10), 'start_login': 'a', 'stop_login': 'b'},
        {'etap': 3, 'czas_start': datetime(2026, 4, 22, 8, 10), 'czas_stop': None, 'start_login': 'a', 'stop_login': None},
        {'etap': 4, 'czas_start': None, 'czas_stop': None, 'start_login': None, 'stop_login': None},
    ]

    result = ZasypEtapyService.get_etapy(plan_id=49, linia='AGRO')

    etap_numbers = [item['etap'] for item in result['etapy']]
    assert etap_numbers == [1, 2, 3, 4, 5]
    assert result['active_etap'] == 3


@patch('app.services.zasyp_etapy_service.get_db_connection')
def test_start_etap_allows_agro_stage_3(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    mock_cursor.fetchall.return_value = [
        (1, datetime(2026, 4, 22, 8, 0), datetime(2026, 4, 22, 8, 5)),
        (2, datetime(2026, 4, 22, 8, 5), datetime(2026, 4, 22, 8, 10)),
    ]

    mock_cursor.fetchone.side_effect = [
        (1,),
        None,
        None,
    ]

    ok, msg = ZasypEtapyService.start_etap(plan_id=49, linia='AGRO', data_planu=datetime(2026, 4, 22).date(), etap=3, user_login='test')
    assert ok is True
    assert 'Start etapu 3 zapisany' in msg


@patch('app.services.zasyp_etapy_service.get_db_connection')
def test_restart_completed_agro_stage_4(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    mock_cursor.fetchall.return_value = [
        (1, datetime(2026, 4, 22, 8, 0), datetime(2026, 4, 22, 8, 5)),
        (2, datetime(2026, 4, 22, 8, 5), datetime(2026, 4, 22, 8, 10)),
        (3, datetime(2026, 4, 22, 8, 10), datetime(2026, 4, 22, 8, 12)),
        (4, datetime(2026, 4, 22, 8, 12), datetime(2026, 4, 22, 8, 15)),
        (31, datetime(2026, 4, 22, 8, 15), datetime(2026, 4, 22, 8, 18)),
    ]

    mock_cursor.fetchone.side_effect = [
        (1,),
        None,
        (datetime(2026, 4, 22, 8, 10), datetime(2026, 4, 22, 8, 15)),
        None,
    ]

    ok, msg = ZasypEtapyService.start_etap(plan_id=49, linia='AGRO', data_planu=datetime(2026, 4, 22).date(), etap=4, user_login='test')
    assert ok is True
    assert 'Dodano kolejną sekcję: 41' in msg
