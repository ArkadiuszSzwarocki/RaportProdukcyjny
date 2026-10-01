import pytest
from flask import Blueprint, Flask
from unittest.mock import Mock

from app.blueprints.api.scanner_sync import register_api_scanner_sync_routes
from app.core.browser_security import register_browser_security_headers


@pytest.fixture
def offline_client(monkeypatch):
    app = Flask(__name__, static_folder=None)
    app.secret_key = 'test-offline-owner'
    bp = Blueprint('offline_test', __name__)
    register_api_scanner_sync_routes(bp)
    app.register_blueprint(bp)
    register_browser_security_headers(app)
    process = Mock(return_value={'items': []})
    monkeypatch.setattr('app.services.scanner_sync_service.ScannerSyncService.process_sync_batch', process)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(zalogowany=True, user_id=29, login='current-user')
    return client, process


@pytest.mark.parametrize('owner', [None, '', '17', 'anonymous'])
def test_scanner_rejects_queue_without_matching_owner(offline_client, owner):
    client, process = offline_client
    response = client.post('/api/scanner/sync-batch', json={
        'owner_user_id': owner, 'events': [{'client_uuid': 'scan', 'scanned_code': 'code'}],
    })
    assert response.status_code == 403
    process.assert_not_called()


def test_scanner_uses_authenticated_login(offline_client):
    client, process = offline_client
    events = [{'client_uuid': 'scan', 'scanned_code': 'code'}]
    response = client.post('/api/scanner/sync-batch', json={'owner_user_id': '29', 'events': events})
    assert response.status_code == 200
    process.assert_called_once_with(events=events, user_login='current-user')


def test_stale_tab_header_blocks_generic_mutation():
    app = Flask(__name__, static_folder=None)
    app.secret_key = 'test-offline-header'
    mutation = Mock(return_value='saved')
    app.add_url_rule('/mutation', view_func=lambda: mutation(), endpoint='mutation', methods=['POST'])
    register_browser_security_headers(app)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(zalogowany=True, user_id=29, login='current-user')
    response = client.post('/mutation', headers={'X-RP-Offline-Owner': '17'})
    assert response.status_code == 403
    mutation.assert_not_called()
    assert client.post('/mutation', headers={'X-RP-Offline-Owner': '29'}).status_code == 200
    mutation.assert_called_once()


@pytest.mark.parametrize('payload', [[], {'owner_user_id': '29', 'events': [1]},
                                     {'owner_user_id': '29', 'events': [{}] * 501}])
def test_invalid_batch_never_reaches_sync_service(offline_client, payload):
    client, process = offline_client
    assert client.post('/api/scanner/sync-batch', json=payload).status_code == 400
    process.assert_not_called()
