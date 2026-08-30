import pytest
from unittest.mock import patch
from printer_server.server import app

@pytest.fixture
def printer_client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@patch('printer_server.server.wyslij_do_drukarki')
def test_drukuj_zpl_single_copy(mock_send, printer_client):
    mock_send.return_value = True
    res = printer_client.post('/drukuj-zpl', json={
        'ip': '192.168.1.100',
        'copies': 1,
        'dane': {
            'palletData': {
                'nrPalety': 'PAL123',
                'productName': 'Testowy Produkt',
                'currentWeight': 500
            }
        }
    })
    assert res.status_code == 200
    assert mock_send.called
    zpl = mock_send.call_args[0][0]
    assert '^PQ' not in zpl
    assert '^XZ' in zpl

@patch('printer_server.server.wyslij_do_drukarki')
def test_drukuj_zpl_multiple_copies(mock_send, printer_client):
    mock_send.return_value = True
    res = printer_client.post('/drukuj-zpl', json={
        'ip': '192.168.1.100',
        'copies': 2,
        'dane': {
            'palletData': {
                'nrPalety': 'PAL123',
                'productName': 'Testowy Produkt',
                'currentWeight': 500
            }
        }
    })
    assert res.status_code == 200
    assert mock_send.called
    zpl = mock_send.call_args[0][0]
    assert '^PQ2' in zpl
    assert '^XZ' in zpl

@patch('printer_server.server.wyslij_do_drukarki')
def test_drukuj_zpl_raw_string_with_copies(mock_send, printer_client):
    mock_send.return_value = True
    raw_zpl = "^XA^FO50,50^ADN,36,20^FDRAW TEST^FS^XZ"
    res = printer_client.post('/drukuj-zpl', json={
        'ip': '192.168.1.100',
        'copies': 2,
        'dane': raw_zpl
    })
    assert res.status_code == 200
    assert mock_send.called
    zpl = mock_send.call_args[0][0]
    assert '^PQ2' in zpl
    assert '^XZ' in zpl
