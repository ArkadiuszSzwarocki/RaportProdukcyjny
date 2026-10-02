from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services import mqtt_service
from app.services.print_server import PrintServer
from printer_server import server


def test_no_wrapper_print_trigger_remains():
    from app.core import daemon
    assert not hasattr(daemon, '_print_wrapped_pallet_label_once')
    source = Path(daemon.__file__).read_text(encoding='utf-8')
    assert 'plan_wrap_states' not in source
    assert 'current_wrapped' not in source


def test_partial_send_is_not_retried():
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.sendall.side_effect = OSError('connection lost after some bytes')
    with patch.object(server.socket, 'create_connection', return_value=sock) as connect:
        with pytest.raises(server.PrintOutcomeUnknown):
            server.wyslij_do_drukarki('^XA^PQ2^XZ', '192.0.2.1', port=9100, retries=3, retry_delay=0)
    assert connect.call_count == 1
    assert sock.sendall.call_count == 1


def test_error_status_after_send_does_not_resend():
    sock = MagicMock()
    sock.__enter__.return_value = sock
    with patch.object(server.socket, 'create_connection', return_value=sock), \
         patch.object(server, 'sprawdz_stan_fizyczny_zebra', return_value=(False, 'paused')):
        with pytest.raises(server.PrintOutcomeUnknown):
            server.wyslij_do_drukarki('^XA^PQ2^XZ', '192.0.2.1', port=9100, retries=3, retry_delay=0)
    assert sock.sendall.call_count == 1


def test_connect_failure_can_retry_before_sending():
    sock = MagicMock()
    sock.__enter__.return_value = sock
    with patch.object(server.socket, 'create_connection', side_effect=[ConnectionRefusedError(), sock]), \
         patch.object(server, 'sprawdz_stan_fizyczny_zebra', return_value=(True, 'OK')):
        assert server.wyslij_do_drukarki('^XA^XZ', '192.0.2.1', port=9100, retries=2, retry_delay=0)
    assert sock.sendall.call_count == 1


def test_post_response_loss_is_not_retried_by_autostart():
    printer = PrintServer()
    printer.bridge_autostart = True
    with patch.object(printer, '_is_local_bridge_target', return_value=True), \
         patch.object(printer, '_ensure_bridge_running') as autostart, \
         patch('app.services.print_server.requests.request', side_effect=requests.ReadTimeout()) as request:
        ok, message = printer._send_to_bridge({'dane': '^XA^XZ'})
    assert not ok
    assert 'WYNIK_NIEPEWNY:' in message
    assert request.call_count == 1
    autostart.assert_not_called()


def test_unknown_bridge_outcome_is_propagated():
    response = MagicMock(status_code=409)
    response.json.return_value = {'success': False, 'outcome_unknown': True, 'message': 'check printer'}
    with patch('app.services.print_server.requests.request', return_value=response):
        ok, message = PrintServer()._send_to_bridge({'dane': '^XA^XZ'})
    assert not ok
    assert 'WYNIK_NIEPEWNY:' in message


def test_invalid_mqtt_json_is_rejected_without_file_write():
    with patch('builtins.open', side_effect=AssertionError('No hardcoded log write')):
        mqtt_service.on_message(None, None, SimpleNamespace(topic='agroPaletyzator', payload=b'not JSON'))


def test_two_labels_still_requested():
    assert '^PQ2' in PrintServer().build_finished_product_label_zpl({'nr_palety': 'AUDIT'}, copies=2)


def test_windows_spool_failure_after_write_is_uncertain():
    import sys
    windows_printer = MagicMock()
    windows_printer.WritePrinter.side_effect = OSError('spool response lost')
    with patch.dict(sys.modules, {'win32print': windows_printer}):
        with pytest.raises(server.PrintOutcomeUnknown):
            server.wyslij_do_drukarki_win32('^XA^PQ2^XZ', 'Audit')
    assert windows_printer.WritePrinter.call_count == 1


def test_spooler_holds_uncertain_job_for_review():
    from app.core import daemon

    class StopLoop(BaseException):
        pass

    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.rowcount = 1
    cursor.fetchall.return_value = [{
        'id': 123, 'printer_ip': '192.0.2.1', 'printer_name': 'Audit',
        'zpl_content': '^XA^PQ2^XZ', 'retry_count': 0,
    }]
    printer = MagicMock()
    printer.test_connection.return_value = (True, 'OK')
    printer._send_to_bridge.return_value = (False, 'WYNIK_NIEPEWNY: response lost')
    with patch('app.db.get_db_connection', return_value=conn), \
         patch('app.services.print_server.PrintServer', return_value=printer), \
         patch.object(daemon.time, 'sleep', side_effect=StopLoop):
        with pytest.raises(StopLoop):
            daemon._print_spooler_loop()
    held = [call for call in cursor.execute.call_args_list if "retry_count=3" in str(call.args[0]) and len(call.args) == 2]
    assert len(held) == 1
    assert held[0].args[1] == ('WYNIK_NIEPEWNY: response lost', 123)
    assert printer._send_to_bridge.call_count == 1
