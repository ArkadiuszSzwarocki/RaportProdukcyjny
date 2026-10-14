"""Dosypka polling must enforce login and the actual Zasyp page grant."""
from unittest.mock import MagicMock, patch

import pytest


def test_anonymous_badge_polling_is_denied_before_database_access(client):
    with patch('app.blueprints.production.notifications.get_db_connection') as database:
        response = client.get('/api/zasyp/pending_dosypki_badges?linia=AGRO',
                              headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 401
    database.assert_not_called()


@pytest.mark.parametrize('permission,error,status', [(False, None, 403), (None, RuntimeError('unavailable'), 503)])
def test_badge_polling_denies_missing_page_permission_and_lookup_failure(client, permission, error, status):
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='laborant', grupa='AGRO')
    with patch('app.core.production_permissions._page_allowed', return_value=permission, side_effect=error) as allowed, patch(
            'app.blueprints.production.notifications.get_db_connection') as database:
        response = client.get('/api/zasyp/pending_dosypki_badges?linia=AGRO')
    assert response.status_code == status
    allowed.assert_called_once_with('AGRO', 'zasyp', write=False)
    database.assert_not_called()


def test_readonly_page_grant_can_read_only_its_batch_counts(client):
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='laborant', grupa='AGRO')
    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = [(323, 558, 1)]
    with patch('app.core.production_permissions._page_allowed', return_value=True), patch(
            'app.blueprints.production.notifications.get_db_connection', return_value=connection):
        response = client.get('/api/zasyp/pending_dosypki_badges?linia=AGRO')
    assert response.status_code == 200
    assert response.get_json()['batch_counts'] == {'323': {'558': 1}}
