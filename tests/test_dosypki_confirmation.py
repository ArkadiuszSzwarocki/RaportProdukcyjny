"""Exercise confirmation through the production permission guard without real writes."""
# cspell:words wydozowane
from unittest.mock import MagicMock, patch
import pytest

from flask import Blueprint, Flask

from app.blueprints.production.dosypki import register_production_dosypki_routes
from app.core.production_permissions import enforce_production_write


@pytest.mark.parametrize('next_stage', [None, 3, 31])
def test_confirmation_form_passes_guard_and_records_actual_weight(next_stage):
    app = Flask(__name__)
    app.secret_key = 'isolated-confirmation-test'
    blueprint = Blueprint('production', __name__)
    updated = MagicMock()
    register_production_dosypki_routes(blueprint, lambda: '/', MagicMock(), updated, MagicMock())
    app.register_blueprint(blueprint)
    app.before_request(enforce_production_write)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL', pracownik_id=17)
    permission_connection = MagicMock()
    permission_connection.cursor.return_value.fetchone.side_effect = [(323,), ('Zasyp',)]
    action_connection = MagicMock()
    action_connection.cursor.return_value.fetchone.side_effect = [(323, 558), (323,), (91,)]
    with patch('app.core.production_permissions.get_db_connection', return_value=permission_connection), patch(
        'app.blueprints.production.dosypki.get_db_connection', return_value=action_connection), patch(
        'app.blueprints.production.dosypki.sync_dosypka_notifications'), patch(
        'app.blueprints.production.dosypki.ZasypEtapyService.advance_after_confirmed_dosypka',
        return_value=next_stage) as advance:
        response = client.post('/potwierdz_dosypke/91?linia=AGRO', data={'kg': '45'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    assert response.get_json()['next_stage'] == next_stage
    advance.assert_called_once_with(action_connection.cursor.return_value, 323, 558, 'pytest')
    writes = action_connection.cursor.return_value.execute.call_args_list
    assert any('kg_wydozowane=%s' in call.args[0] and call.args[1] == (45.0, 45.0, 17, 91) for call in writes)
    assert any('tonaz_rzeczywisty' in call.args[0] for call in writes)
    action_connection.commit.assert_called_once()
    updated.assert_called_once_with('AGRO')


@pytest.mark.parametrize('weight', ['0', '-1', 'nan', 'inf', '1e999', 'abc'])
def test_confirmation_rejects_invalid_weight_without_writes(weight):
    app = Flask(__name__)
    app.secret_key = 'isolated-confirmation-test'
    blueprint = Blueprint('production', __name__)
    register_production_dosypki_routes(blueprint, lambda: '/', MagicMock(), MagicMock(), MagicMock())
    app.register_blueprint(blueprint)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='masteradmin')
    connection = MagicMock()
    connection.cursor.return_value.fetchone.side_effect = [(323, 558), (323,), (91,)]
    with patch('app.blueprints.production.dosypki.get_db_connection', return_value=connection):
        response = client.post('/potwierdz_dosypke/91?linia=AGRO', data={'kg': weight},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 400
    assert response.get_json()['success'] is False
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    assert not any(call.args[0].startswith('UPDATE') for call in connection.cursor.return_value.execute.call_args_list)
