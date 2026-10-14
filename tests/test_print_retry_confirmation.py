from unittest.mock import MagicMock, patch
import pytest
from flask import Blueprint, Flask
from app.blueprints.admin.system import register_admin_system_routes


@pytest.fixture
def retry_client():
    app = Flask(__name__)
    app.secret_key = 'local-test-only'
    bp = Blueprint('admin', __name__)
    register_admin_system_routes(bp, list_online_users=lambda: [])
    app.register_blueprint(bp)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='admin')
    conn = MagicMock()
    with patch('app.db.get_db_connection', return_value=conn), \
         patch('app.core.contexts.inject_role_permissions', return_value={}):
        yield client, conn


def test_uncertain_retry_requires_explicit_confirmation(retry_client):
    client, conn = retry_client
    conn.cursor.return_value.fetchone.return_value = ('ERROR', 'WYNIK_NIEPEWNY: response lost')
    response = client.post('/admin/api/print-jobs/retry/10', json={})
    assert response.status_code == 409
    assert response.json['requires_confirmation']
    conn.commit.assert_not_called()


def test_confirmed_uncertain_retry_can_be_queued(retry_client):
    client, conn = retry_client
    conn.cursor.return_value.fetchone.return_value = ('ERROR', 'WYNIK_NIEPEWNY: response lost')
    response = client.post('/admin/api/print-jobs/retry/10', json={'confirm_uncertain': True})
    assert response.status_code == 200
    conn.commit.assert_called_once()


@pytest.mark.parametrize('status', ['DONE', 'PRINTING', 'PENDING'])
def test_completed_or_active_job_cannot_be_retried(retry_client, status):
    client, conn = retry_client
    conn.cursor.return_value.fetchone.return_value = (status, None)
    assert client.post('/admin/api/print-jobs/retry/10', json={'confirm_uncertain': True}).status_code == 409
    conn.commit.assert_not_called()
