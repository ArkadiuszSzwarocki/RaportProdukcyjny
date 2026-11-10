from app.services.agro.agro_tanks_service import AgroTanksService
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _session_active_guard():
    with patch('app.core.middleware.is_session_active', return_value=True):
        yield


def _login_as_admin(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'admin'
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['rola'] = 'admin'
        sess['pracownik_id'] = 1


def _allow_all_permissions():
    return {'role_has_access': lambda _page_name: True}


def test_snapshot_endpoint_defaults_show_empty_false(client):
    _login_as_admin(client)
    fake_items = [{'zbiornik': 'BB01', 'stan_systemowy': 125.0, 'is_empty': False}]

    with patch(
        'app.blueprints.agro_warehouse.api_inventory.AgroTanksService.get_production_inventory_snapshot',
        return_value=fake_items,
    ) as mock_snapshot:
        response = client.get('/agro/api/production_inventory_snapshot?linia=AGRO')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['count'] == 1
    assert payload['items'][0]['zbiornik'] == 'BB01'
    mock_snapshot.assert_called_once_with(limit=4000, linia='AGRO', show_empty=False)


def test_snapshot_endpoint_accepts_show_empty_flag(client):
    _login_as_admin(client)
    fake_items = [{'zbiornik': 'BB01', 'stan_systemowy': 0.0, 'is_empty': True}]

    with patch(
        'app.blueprints.agro_warehouse.api_inventory.AgroTanksService.get_production_inventory_snapshot',
        return_value=fake_items,
    ) as mock_snapshot:
        response = client.get('/agro/api/production_inventory_snapshot?linia=AGRO&limit=123&show_empty=1')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['count'] == 1
    assert payload['items'][0]['is_empty'] is True
    mock_snapshot.assert_called_once_with(limit=123, linia='AGRO', show_empty=True)


def test_tank_history_endpoint_renders_history_page(client):
    _login_as_admin(client)
    fake_history = [
        {
            'id': 101,
            'typ_ruchu': 'PRODUKCJA',
            'ilosc': -120.0,
            'ilosc_po': 320.0,
            'status': 'POTWIERDZONE',
            'autor_login': 'operator',
            'autor_data': '28.05.2026 10:20',
            'komentarz': 'Testowy ruch',
            'surowiec_nazwa': 'Maka pszenna',
            'plan_id': 77,
            'plan_name': 'Produkt X',
            'zbiornik': 'BB01',
        }
    ]

    with patch('app.core.contexts.inject_role_permissions', return_value=_allow_all_permissions()), patch(
        'app.blueprints.agro_warehouse.api_inventory.AgroTanksService.get_production_tank_history',
        return_value=fake_history,
    ) as mock_history:
        response = client.get('/agro/magazyn/inwentaryzacja-produkcji/historia-stara/BB01?linia=AGRO')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Historia zbiornika BB01' in body
    assert 'Maka pszenna' in body
    mock_history.assert_called_once_with('BB01', limit=300, linia='AGRO')


def test_tank_history_endpoint_redirects_for_invalid_tank(client):
    _login_as_admin(client)

    with patch('app.core.contexts.inject_role_permissions', return_value=_allow_all_permissions()):
        response = client.get(
            '/agro/magazyn/inwentaryzacja-produkcji/historia-stara/XYZ?linia=AGRO',
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert '/agro/magazyn/inwentaryzacja-produkcji?linia=AGRO' in response.headers['Location']


def test_production_materials_include_every_ko_station():
    from flask import Flask
    from app.blueprints.agro_warehouse.views import surowce_w_produkcji
    snapshot = [{'zbiornik': f'KO{i:02d}', 'stan_systemowy': 0} for i in range(1, 41)]
    application = Flask(__name__)
    view = surowce_w_produkcji
    while hasattr(view, '__wrapped__'):
        view = view.__wrapped__
    with application.test_request_context('/?linia=AGRO'), patch(
        'app.blueprints.agro_warehouse.views.AgroTanksService.get_production_inventory_snapshot', return_value=snapshot
    ), patch('app.blueprints.agro_warehouse.views.render_template', return_value='OK') as render:
        assert view() == 'OK'
    groups = render.call_args.kwargs['grouped_entries']
    assert [item['zbiornik'] for items in groups.values() for item in items] == [f'KO{i:02d}' for i in range(1, 41)]


def test_nonexistent_k_stations_are_not_offered_or_accepted():
    from app.repositories.agro_tanks_repository import AgroTanksRepository
    from app.utils.location_validator import validate_production_tank
    from app.services.tank_validation_service import TankValidationService
    codes = AgroTanksRepository.get_production_tanks()['ALL']
    assert all(f'KO{i:02d}' in codes for i in range(1, 41))
    assert not any(code.startswith('K') and not code.startswith('KO') for code in codes)
    assert not validate_production_tank('K001')[0]
    with patch('app.services.tank_validation_service.TankValidationRepository.upsert_rule') as write:
        assert not TankValidationService.save_tank_rule('K001', 'Mąka')[0]
        write.assert_not_called()
