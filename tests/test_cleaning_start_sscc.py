from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from flask import Blueprint, Flask

from app.blueprints.production.orders import register_production_order_routes


@pytest.mark.parametrize('override', [False, True])
@pytest.mark.parametrize('sscc', ['', '   ', 'SUR000001234567890123'])
def test_cleaning_start_requires_sscc_even_when_masteradmin_overrides_queue(override, sscc):
    app = Flask(__name__)
    app.secret_key = 'cleaning-start-test-only'
    blueprint = Blueprint('production', __name__)
    register_production_order_routes(blueprint, lambda: '/')
    app.register_blueprint(blueprint)
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (
        'Czyszczenie', 100, 'Zasyp', date(2026, 10, 19), 'NORMAL', 'zaplanowane', 0,
        None, None, None, '',
    )
    cursor.fetchall.return_value = [(1, 'Inne', 'w toku')] if override else []
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    with patch('app.blueprints.production.orders.get_db_connection', return_value=connection), \
         patch('app.blueprints.production.orders.audit_log'), \
         patch('app.db.create_notifications'), patch('app.db.refresh_bufor_queue'):
        response = client.post('/start_zlecenie/2', data={
            'linia': 'AGRO', 'override_start_rule': '1' if override else '0', 'skan_sscc': sscc,
        })
    assert response.status_code == 302
    sql_calls = cursor.execute.call_args_list
    if not sscc.strip():
        assert not any(call.args[0].lstrip().startswith(('UPDATE', 'INSERT', 'DELETE')) for call in sql_calls)
        connection.commit.assert_not_called()
        with client.session_transaction() as state:
            assert any('SSCC palety do czyszczenia' in message for _, message in state['_flashes'])
    else:
        assert any('SET skan_sscc=%s' in call.args[0] and call.args[1] == (sscc, 2) for call in sql_calls)
        assert any("SET status='w toku'" in call.args[0] for call in sql_calls)


@pytest.mark.parametrize('status', ['zawieszone', 'wstrzymane'])
@pytest.mark.parametrize('saved_sscc', [None, '  ', 'SUR000001234567890123'])
def test_resume_reuses_saved_cleaning_sscc_without_consuming_pallet_again(status, saved_sscc):
    app = Flask(__name__)
    app.secret_key = 'cleaning-resume-test-only'
    blueprint = Blueprint('production', __name__)
    register_production_order_routes(blueprint, lambda: '/')
    app.register_blueprint(blueprint)
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [
        ('Czyszczenie', 100, 'Zasyp', date(2026, 10, 19), 'NORMAL', status, 0,
         None, None, None, ''),
        (saved_sscc,),
    ]
    cursor.fetchall.return_value = [(1, 'Inne', 'w toku')]
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    with patch('app.blueprints.production.orders.get_db_connection', return_value=connection), \
         patch('app.blueprints.production.orders.audit_log'), \
         patch('app.db.create_notifications'), patch('app.db.refresh_bufor_queue'):
        response = client.post('/start_zlecenie/2', data={'linia': 'AGRO', 'override_start_rule': '1'})
    assert response.status_code == 302
    updates = [call.args[0] for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
    if saved_sscc and saved_sscc.strip():
        assert any("SET status='w toku'" in sql for sql in updates)
        assert not any('SET skan_sscc' in sql or 'stan_magazynowy' in sql for sql in updates)
    else:
        assert updates == []
