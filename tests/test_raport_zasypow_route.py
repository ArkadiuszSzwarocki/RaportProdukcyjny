import pytest
from unittest.mock import patch

@patch('app.services.zasypy_raport_service.ZasypyRaportService.get_zasypy_report')
def test_raport_zasypow_renders_successfully(mock_service, client):
    mock_service.return_value = [
        {
            'linia': 'PSD',
            'zasyp_id': 101,
            'nr_zasypu': 1,
            'nr_szarzy': 12,
            'waga_zasypu': 1000.0,
            'data_zasypu': None,
            'plan_id': 50,
            'data_planu': '2026-08-19',
            'produkt': 'Cukier puder',
            'nazwa_zlecenia': 'ZL/2026/01',
            'plan_status': 'ZAKONCZONE',
            'zasyp_pracownik': 'jan_kowalski',
            'dosypki': [
                {
                    'id': 5,
                    'nazwa': 'Dodatek A',
                    'waga': 2.5,
                    'data': None,
                    'potwierdzone': 1,
                    'data_potwierdzenia': None,
                    'zlecil': 'lider1',
                    'potwierdzil': 'operator1'
                }
            ]
        }
    ]

    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['rola'] = 'admin'

    res = client.get('/raporty/zasypy-dosypki?linia=PSD&start_date=2026-08-10&end_date=2026-08-19')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'Raport Zasypów i Dosypek' in html
    assert 'Cukier puder' in html
    assert 'Dodatek A' in html
