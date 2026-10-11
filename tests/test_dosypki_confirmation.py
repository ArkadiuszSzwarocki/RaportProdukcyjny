"""Exercise confirmation through the production permission guard without real writes."""
# cspell:words wydozowane
from unittest.mock import MagicMock, patch

from flask import Blueprint, Flask

from app.blueprints.production.dosypki import register_production_dosypki_routes
from app.core.production_permissions import enforce_production_write


def test_confirmation_form_passes_guard_and_records_actual_weight():
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
    action_connection.cursor.return_value.fetchone.side_effect = [(91,), (323,)]
    with patch('app.core.production_permissions.get_db_connection', return_value=permission_connection), patch(
        'app.blueprints.production.dosypki.get_db_connection', return_value=action_connection), patch(
        'app.blueprints.production.dosypki.sync_dosypka_notifications'):
        response = client.post('/potwierdz_dosypke/91?linia=AGRO', data={'kg': '45'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    writes = action_connection.cursor.return_value.execute.call_args_list
    assert any('kg_wydozowane=%s' in call.args[0] and call.args[1] == (45.0, 45.0, 17, 91) for call in writes)
    assert any('tonaz_rzeczywisty' in call.args[0] for call in writes)
    action_connection.commit.assert_called_once()
    updated.assert_called_once_with('AGRO')
