"""Confirmed additions are cancelled individually without erasing their history."""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Blueprint, Flask
from jinja2 import ChainableUndefined

from app.blueprints.production.dosypki import register_production_dosypki_routes
from app.repositories.production_repository import cancel_confirmed_dosypka


@pytest.mark.parametrize('line', ['AGRO', 'PSD'])
def test_confirmed_cancellation_preserves_confirmation_and_records_actor(line):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (91, 323, 'Protein Mix', 55.4, 1, 0)
    with patch('app.repositories.production_repository.get_db_connection', return_value=connection):
        ok, _, plan_id = cancel_confirmed_dosypka(91, 'supervisor', line)
    assert ok and plan_id == 323
    calls = cursor.execute.call_args_list
    assert 'FOR UPDATE' in calls[0].args[0]
    cancellation = next(c for c in calls if 'SET anulowana=1' in c.args[0])
    assert cancellation.args[1] == ('supervisor (MasterAdmin - anulowano zatwierdzoną)', 91)
    assert 'data_anulowania=NOW()' in cancellation.args[0]
    assert 'potwierdzone=0' not in cancellation.args[0]
    assert 'DELETE' not in ' '.join(c.args[0] for c in calls)
    assert any('tonaz_rzeczywisty' in c.args[0] and 'COALESCE(anulowana, 0) = 0' in c.args[0] for c in calls)
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize('row', [None, (91, 323, 'Mix', 5, 1, 1), (91, 323, 'Mix', 5, 0, 0)])
def test_missing_cancelled_or_unconfirmed_addition_is_not_changed(row):
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = row
    with patch('app.repositories.production_repository.get_db_connection', return_value=connection):
        ok, _, _ = cancel_confirmed_dosypka(91, 'supervisor', 'AGRO')
    assert not ok
    connection.commit.assert_not_called()
    assert len(connection.cursor.return_value.execute.call_args_list) == 1
    connection.close.assert_called_once()


def make_client(role):
    app = Flask(__name__)
    app.secret_key = 'isolated-cancellation-test'
    blueprint = Blueprint('production', __name__)
    updated = MagicMock()
    register_production_dosypki_routes(blueprint, lambda: '/', MagicMock(), updated, MagicMock())
    app.register_blueprint(blueprint)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='test-user', rola=role)
    return client, updated


@pytest.mark.parametrize('role', ['admin', 'laborant', 'operator'])
def test_other_roles_cannot_cancel_confirmed_additions(role):
    client, updated = make_client(role)
    with patch('app.blueprints.production.dosypki.cancel_confirmed_dosypka') as cancel:
        response = client.post('/usun_zatwierdzona_dosypke/91?linia=AGRO',
                               headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 403
    cancel.assert_not_called()
    updated.assert_not_called()


@pytest.mark.parametrize('role', ['masteradmin', 'master_admin', 'Master Admin'])
def test_masteradmin_cancellation_audits_and_notifies(role):
    client, updated = make_client(role)
    with patch('app.blueprints.production.dosypki.cancel_confirmed_dosypka', return_value=(True, 'Anulowana', 323)) as cancel, patch(
        'app.blueprints.production.dosypki.audit_log') as audit, patch(
        'app.blueprints.production.dosypki.sync_dosypka_notifications') as sync:
        response = client.post('/usun_zatwierdzona_dosypke/91?linia=AGRO',
                               headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200 and response.get_json()['success']
    cancel.assert_called_once_with(91, 'test-user', linia='AGRO')
    audit.assert_called_once()
    updated.assert_called_once_with('AGRO')
    sync.assert_called_once()


def test_lab_ajax_cancellation_also_writes_audit_entry():
    client, updated = make_client('laborant')
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = (91, 323)
    with patch('app.blueprints.production.dosypki.get_db_connection', return_value=connection), patch(
        'app.blueprints.production.dosypki.audit_log') as audit:
        response = client.post('/anuluj_dosypke/91?linia=AGRO',
                               headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200 and response.get_json()['success']
    audit.assert_called_once()
    assert 'anulowal=test-user' in audit.call_args.args[1]
    assert 'FOR UPDATE' in connection.cursor.return_value.execute.call_args_list[0].args[0]
    connection.commit.assert_called_once()


def test_quality_history_shows_cancelled_actor_time_and_confirmation():
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    addition = dict(id=91, nazwa='Protein Mix', kg=55.4, anulowana=1, potwierdzone=1,
                    anulowal_login='MasterAdmin', data_anulowania='2026-10-15 20:00', data_zlecenia='2026-10-15 19:00')
    with app.test_request_context('/'):
        html = app.jinja_env.get_template('jakosc_podsumowanie_szarz_fragment.html').render(
            szarze=[dict(szarza_id=558, plan_id=323, dosypki=[addition])])
    assert 'Anulowana' in html and 'MasterAdmin' in html and '2026-10-15 20:00' in html
    assert 'Protein Mix' in html and '#91' in html


@pytest.mark.parametrize('role', ['masteradmin', 'laborant', 'admin', 'operator'])
def test_dashboard_exposes_cancellation_for_masteradmin_and_keeps_duplicate_ids(role):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, role_is_readonly=lambda page: False,
                       url_for=lambda endpoint, **kw: '/' + endpoint + '/' + str(kw.get('dosypka_id', '')))
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_agro_active_details.html').render(
            rola=role, linia='AGRO', sekcja='Zasyp', p=(323, 'Mix', 400, 'w toku'), dzisiaj=date.today(),
            palety_mapa={323: [(110.8, '12:00', 558, [('Protein Mix', 55.4, 50, 91), ('Protein Mix', 55.4, 50, 92)], 'Zarejestrowana', 'operator')]})
    assert html.count('data-action="cancel-confirmed-dosypka"') == (2 if role == 'masteradmin' else 0)
    if role == 'masteradmin':
        assert 'Anuluj #91' in html and 'Anuluj #92' in html
