# cspell:words FDNR FDQA XZJA
from unittest.mock import MagicMock, patch

import pytest

from app.services.print_server import PrintServer


@pytest.mark.parametrize('line', ['AGRO', 'PSD'])
def test_finished_product_label_keeps_sequence_separate_from_sscc_and_batch(line):
    zpl = PrintServer().build_finished_product_label_zpl({
        'linia': line,
        'nrPalety': 'AGR000001234567890123',
        'nr_palety_lp': 27,
        'nr_partii': '26-292',
        'ilosc': 1000,
    }, copies=2)

    assert '^FO40,750^A0N,50,50^FDNR PALETY: 27^FS' in zpl
    assert '^FDQA,AGR000001234567890123^FS' in zpl
    assert '^FDNR PARTII: 26-292^FS' in zpl
    assert '"lp": "27"' in zpl
    assert '^PQ2' in zpl


def test_finished_product_label_does_not_invent_missing_sequence():
    zpl = PrintServer().build_finished_product_label_zpl({'nrPalety': 'AGR-123'})
    assert '^FDNR PALETY: ---^FS' in zpl


def test_finished_product_label_sanitizes_sequence_as_zpl_text():
    zpl = PrintServer().build_finished_product_label_zpl({'nr_palety_lp': '27^XZ~JA'})
    assert '^FDNR PALETY: 27XZJA^FS' in zpl
    assert zpl.count('^XZ') == 1


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

    with patch('app.services.print_server.requests.request', return_value=(response)):
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

    with patch('app.services.print_server.requests.request', return_value=(response)):
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

    with patch('app.services.print_server.requests.request', side_effect=Exception('boom')):
        ok, message = service._send_to_bridge(payload)

    assert ok is False
    assert 'Błąd komunikacji z mostkiem' in message
    assert 'boom' in message
    assert 'drukarka=Zebra Produkcja' in message
    assert 'ip=192.168.1.240' in message
