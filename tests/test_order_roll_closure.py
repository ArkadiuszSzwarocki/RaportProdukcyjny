# cspell:words pozostalo
"""Order and roll closure must use one transaction and print only after commit."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from flask import Blueprint, Flask

from app.services.folio_service import FolioService


def roll_connection():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [
        {'plan_id': 2, 'opakowanie_id': 3, 'stan_poczatkowy': 1000,
         'licznik_start': 10, 'opak_nazwa': 'Film'},
        {'data_planu': date(2026, 10, 25), 'produkt': 'Milk'},
        None, None,
        {'nr_palety': 'TEST-ROLL', 'nr_partii': 'LOT-1'}]
    return connection, cursor


def test_roll_closure_joins_parent_transaction_and_defers_printing():
    connection, cursor = roll_connection()
    jobs = []
    with patch('app.services.folio_service.get_db_connection', side_effect=AssertionError('No nested connection')), patch(
            'app.services.folio_service._get_mqtt_counter', return_value=48), patch(
            'app.utils.pallet_id.is_valid_pallet_id', return_value=True), patch.object(
            FolioService, 'print_closed_roll_labels') as printer:
        assert FolioService.close_roll(7, 962, 'operator', external_conn=connection, label_jobs=jobs) == (True, None)
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()
    printer.assert_not_called()
    assert len(jobs) == 1 and jobs[0][0]['ilosc'] == 962
    assert 'FOR UPDATE' in cursor.execute.call_args_list[0].args[0]
    updates = [call.args for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE agro_plan_opakowania')]
    assert updates[0][1] == (962.0, 7)


def test_standalone_roll_closure_commits_before_sending_labels():
    connection, _ = roll_connection()
    events = []
    connection.commit.side_effect = lambda: events.append('commit')
    with patch('app.services.folio_service.get_db_connection', return_value=connection), patch(
            'app.services.folio_service._get_mqtt_counter', return_value=48), patch(
            'app.utils.pallet_id.is_valid_pallet_id', return_value=True), patch.object(
            FolioService, 'print_closed_roll_labels', side_effect=lambda jobs: events.append('print')):
        assert FolioService.close_roll(7, 962, 'operator')[0] is True
    assert events == ['commit', 'print']
    connection.close.assert_called_once()


@pytest.mark.parametrize('remaining', [-1, 1001, float('nan'), float('inf')])
def test_invalid_remaining_stock_does_not_write_or_commit(remaining):
    connection, cursor = roll_connection()
    with patch('app.services.folio_service.get_db_connection', return_value=connection):
        assert FolioService.close_roll(7, remaining, 'operator')[0] is False
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_active_roll_read_reuses_order_connection():
    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = []
    with patch('app.services.folio_service.get_db_connection', side_effect=AssertionError('No nested connection')):
        assert FolioService.get_active_rolls(2, external_conn=connection) == []
    connection.close.assert_not_called()


@pytest.mark.parametrize('closed', [True, False])
def test_order_completion_roll_failure_rolls_back_everything(closed):
    from app.blueprints.production.orders import register_production_order_routes
    app = Flask(__name__)
    app.secret_key = 'roll-close-test'
    blueprint = Blueprint('production', __name__)
    register_production_order_routes(blueprint, lambda: '/')
    app.register_blueprint(blueprint)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='operator', rola='masteradmin')
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [('Milk', date(2026, 10, 25), 'w toku'), (10,), (0,), (0,), (0,)]
    cursor.fetchall.return_value = []
    events = []
    connection.commit.side_effect = lambda: events.append('commit')

    def close(*args, **kwargs):
        assert kwargs['external_conn'] is connection
        kwargs['label_jobs'].append(('label', None, None))
        return closed, None if closed else 'Simulated storage failure'

    with patch('app.blueprints.production.orders.get_db_connection', return_value=connection), patch.object(
            FolioService, 'get_active_rolls', return_value=[{'link_id': 7}]) as active, patch.object(
            FolioService, 'close_roll', side_effect=close), patch.object(
            FolioService, 'print_closed_roll_labels', side_effect=lambda jobs: events.append('print')), patch(
            'app.services.mqtt_service.get_latest_data', return_value={}), patch(
            'app.services.mqtt_service.publish_command'), patch('app.blueprints.production.orders.audit_log'), patch(
            'app.db.create_notifications'), patch('app.db.refresh_bufor_queue'):
        response = client.post('/koniec_zlecenie/2', data={'linia': 'AGRO', 'sekcja': 'Workowanie',
            'pozostalo_szt_7': '962'}, headers={'X-Requested-With': 'XMLHttpRequest'})
    active.assert_called_once_with(2, external_conn=connection)
    assert response.status_code == (200 if closed else 500)
    if closed:
        assert events == ['commit', 'print']
        connection.rollback.assert_not_called()
    else:
        assert events == []
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()


def test_repeated_order_completion_does_not_close_or_print_roll_twice():
    from app.blueprints.production.orders import register_production_order_routes
    app = Flask(__name__)
    app.secret_key = 'repeat-close-test'
    blueprint = Blueprint('production', __name__)
    register_production_order_routes(blueprint, lambda: '/')
    app.register_blueprint(blueprint)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='operator', rola='masteradmin')
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = ('Milk', date(2026, 10, 25), 'zakonczone')
    with patch('app.blueprints.production.orders.get_db_connection', return_value=connection), patch.object(
            FolioService, 'close_roll') as close:
        response = client.post('/koniec_zlecenie/2', data={'linia': 'AGRO', 'sekcja': 'Workowanie'},
            headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200 and response.json['success'] is True
    close.assert_not_called()
    assert all(call.args[0].startswith('SELECT') for call in connection.cursor.return_value.execute.call_args_list)
