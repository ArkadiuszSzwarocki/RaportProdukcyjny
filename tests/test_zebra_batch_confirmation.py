from unittest.mock import MagicMock, patch
import pytest
from printer_server import zebra_status as zebra
from printer_server import server

def response(remaining=0, head=0):
    return f'\x02000,0,0,1200,000,0,0,0,000,0,0,0\x03\r\n\x02000,0,{head},0,0,0,0,0,{remaining:08d},1,000\x03\r\n\x020000,0\x03\r\n'

def test_complete_status_uses_second_line():
    status = zebra.parse_host_status(response(2, 1))
    assert status['head_open']
    assert status['labels_remaining'] == 2
    assert not zebra.batch_idle(status)

@pytest.mark.parametrize('raw', ['', 'OK', response().split('\r\n')[0]])
def test_incomplete_status_is_not_success(raw):
    with pytest.raises(ValueError):
        zebra.parse_host_status(raw)

def test_fragmented_status_is_read_completely():
    sock = MagicMock()
    raw = response().encode()
    sock.recv.side_effect = [raw[:25], raw[25:]]
    assert zebra.batch_idle(zebra.read_host_status(sock))

def test_two_copies_require_counter_delta_and_empty_batch():
    with patch.object(zebra, 'read_host_status', side_effect=[zebra.parse_host_status(response(1)), zebra.parse_host_status(response())]), \
         patch.object(zebra, 'read_label_counter', side_effect=[101, 102]), \
         patch.object(zebra.time, 'sleep'):
        assert zebra.wait_for_batch(MagicMock(), 100, 2)

def test_extra_labels_make_confirmation_uncertain():
    with patch.object(zebra, 'read_host_status', return_value=zebra.parse_host_status(response())), \
         patch.object(zebra, 'read_label_counter', return_value=103):
        with pytest.raises(RuntimeError, match='Niejednoznaczna'):
            zebra.wait_for_batch(MagicMock(), 100, 2)

def test_missing_status_does_not_report_ok():
    sock = MagicMock()
    sock.recv.return_value = b''
    assert server.sprawdz_stan_fizyczny_zebra(sock)[0] is False

def test_target_refuses_to_send_when_counter_is_unsupported():
    sock = MagicMock()
    sock.__enter__.return_value = sock
    with patch.object(server.socket, 'create_connection', return_value=sock), \
         patch.object(server, 'read_host_status', return_value=zebra.parse_host_status(response())), \
         patch.object(server, 'read_label_counter', side_effect=ValueError('unsupported')):
        with pytest.raises(ValueError):
            server.wyslij_do_drukarki('^XA^PQ2^XZ', '192.168.1.160')
    sock.sendall.assert_not_called()

def test_target_sends_once_and_waits_for_two_labels():
    sock = MagicMock()
    sock.__enter__.return_value = sock
    with patch.object(server.socket, 'create_connection', return_value=sock), \
         patch.object(server, 'read_host_status', return_value=zebra.parse_host_status(response())), \
         patch.object(server, 'read_label_counter', return_value=100), \
         patch.object(server, 'wait_for_batch', return_value=True) as wait:
        assert server.wyslij_do_drukarki('^XA^PQ2^XZ', '192.168.1.160')
    wait.assert_called_once_with(sock, 100, 2)
    sock.sendall.assert_called_once()

def test_bridge_confirmation_reaches_job_message():
    from app.services.print_server import PrintServer
    reply = MagicMock(status_code=200)
    reply.json.return_value = {'success': True, 'confirmation': 'label_counter', 'copies': 2}
    with patch('app.services.print_server.requests.request', return_value=reply):
        ok, message = PrintServer()._send_to_bridge({'dane': '^XA^PQ2^XZ'})
    assert ok and message.startswith('POTWIERDZONO_LICZNIKIEM:')
