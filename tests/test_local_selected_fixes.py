# cspell:words BOCZKMAR Szwar calkowita
"""Regressions for supervisor authorization and station warehouse lookup."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask
from jinja2 import Environment, FileSystemLoader
import pytest

from app.blueprints.maluchy.api import api_emergency_dump
from app.blueprints.maluchy.permissions import can_emergency_dump_bucket
from app.repositories.station_warehouse_material_repository import StationWarehouseMaterialRepository


@pytest.mark.parametrize('role,login,allowed', [
    ('masteradmin', 'ordinary', True), ('Master Admin', 'ordinary', True),
    ('zarzad', 'ordinary', True), ('zarząd', 'ordinary', True),
    ('pracownik', 'SzwarArk', False), ('laborant', 'BOCZKMAR', False),
    ('lider', 'SzwarArk', False), ('masteradmin', 'BoczkMar', True),
    ('admin', 'ordinary', False), ('lider', 'ordinary', False),
    ('laborant', 'ordinary', False), ('pracownik', 'ordinary', False),
    ('', 'SzwarArk-extra', False),
])
def test_emergency_dump_enforces_supervisor_access(role, login, allowed):
    app = Flask(__name__)
    app.secret_key = 'unit-test-secret'
    app.add_url_rule('/dump', view_func=api_emergency_dump, methods=['POST'])
    with app.test_client() as client:
        with client.session_transaction() as state:
            state.update(zalogowany=True, rola=role, login=login)
        with patch('app.blueprints.maluchy.api.BucketMaluchService.emergency_dump_to_szarza',
                   return_value=(True, 'OK', {})) as change:
            response = client.post('/dump', json={'bucket_id': 1, 'szarza_id': 2, 'plan_id': 3})
        assert response.status_code == (200 if allowed else 403)
        assert change.called == allowed


def test_logged_out_named_account_cannot_use_emergency_action():
    app = Flask(__name__)
    app.secret_key = 'unit-test-secret'
    with app.test_request_context('/'):
        from flask import session
        session.update(login='SzwarArk', rola='masteradmin', zalogowany=False)
        assert not can_emergency_dump_bucket()


@pytest.mark.parametrize('allowed', [True, False])
def test_emergency_action_is_hidden_for_unauthorized_viewers(allowed):
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parents[1] / 'templates')))
    bucket = {'id': 1, 'status': 'skompletowane', 'kod_wiadra': 'W01', 'waga_calkowita': 10}
    html = env.get_template('maluchy/popups/zasyp_wiaderka.html').render(
        summary={'all_buckets': [bucket], 'wrzucone': [], 'skompletowane': [bucket],
                 'w_trakcie': [], 'total_dumped_kg': 0, 'total_ready_kg': 10},
        can_emergency_dump=allowed, plan_id=1, szarza_id=2, linia='AGRO')
    assert ('class="mzp-btn-emergency js-emergency-dump-btn"' in html) == allowed


def test_station_queries_bind_location_before_material_in_both_search_modes():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = []
    with patch('app.repositories.station_warehouse_material_repository.get_db_connection', return_value=connection):
        StationWarehouseMaterialRepository.find_available_pallets_for_assigned_material('Hydro', exclude_location='MP01')
    calls = cursor.execute.call_args_list
    assert calls[0].args[1] == ('MP01', 'HYDRO')
    assert calls[1].args[1] == ('MP01', '%HYDRO%')


def test_station_multiple_material_search_binds_location_before_names():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = []
    with patch('app.repositories.station_warehouse_material_repository.get_db_connection', return_value=connection):
        StationWarehouseMaterialRepository.find_available_pallets_by_material_names(['Hydro', 'Milk'], exclude_location='MP01')
    assert cursor.execute.call_args.args[1] == ('MP01', 'HYDRO', '%HYDRO%', 'MILK', '%MILK%')
