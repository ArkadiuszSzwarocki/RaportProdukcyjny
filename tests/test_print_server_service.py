from unittest.mock import MagicMock, patch

from app.services.print_server import PrintServer


def test_send_to_bridge_success_returns_ok_message():
    service = PrintServer()
    payload = {
        'drukarka': 'Zebra Produkcja',
        'ip': '192.168.1.240',
        'typ': 'finished_product',
        'dane': {'palletData': {'nrPalety': 'AGR-1'}},
    }

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'success': True}

    with patch('app.services.print_server.requests.post', return_value=response):
        ok, message = service._send_to_bridge(payload)

    assert ok is True
    assert 'Wysłano do drukarki' in message


def test_send_to_bridge_failure_contains_printer_target():
    service = PrintServer()
    payload = {
        'drukarka': 'Zebra Produkcja',
        'ip': '192.168.1.240',
        'typ': 'finished_product',
        'dane': {'palletData': {'nrPalety': 'AGR-1'}},
    }

    response = MagicMock()
    response.status_code = 500
    response.json.return_value = {'success': False, 'message': 'Timeout połączenia z drukarką'}

    with patch('app.services.print_server.requests.post', return_value=response):
        ok, message = service._send_to_bridge(payload)

    assert ok is False
    assert 'Timeout połączenia z drukarką' in message
    assert 'drukarka=Zebra Produkcja' in message
    assert 'ip=192.168.1.240' in message


def test_send_to_bridge_exception_contains_printer_target():
    service = PrintServer()
    payload = {
        'drukarka': 'Zebra Produkcja',
        'ip': '192.168.1.240',
        'typ': 'finished_product',
        'dane': {'palletData': {'nrPalety': 'AGR-1'}},
    }

    with patch('app.services.print_server.requests.post', side_effect=Exception('boom')):
        ok, message = service._send_to_bridge(payload)

    assert ok is False
    assert 'Błąd komunikacji z mostkiem' in message
    assert 'boom' in message
    assert 'drukarka=Zebra Produkcja' in message
    assert 'ip=192.168.1.240' in message
