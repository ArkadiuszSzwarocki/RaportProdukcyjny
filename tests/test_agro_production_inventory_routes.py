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
        'app.blueprints.agro_warehouse.base.AgroWarehouseService.get_production_inventory_snapshot',
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
        'app.blueprints.agro_warehouse.base.AgroWarehouseService.get_production_inventory_snapshot',
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
        'app.blueprints.agro_warehouse.base.AgroWarehouseService.get_production_tank_history',
        return_value=fake_history,
    ) as mock_history:
        response = client.get('/agro/magazyn/inwentaryzacja-produkcji/historia/BB01?linia=AGRO')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Historia zbiornika BB01' in body
    assert 'Maka pszenna' in body
    mock_history.assert_called_once_with('BB01', limit=300, linia='AGRO')


def test_tank_history_endpoint_redirects_for_invalid_tank(client):
    _login_as_admin(client)

    with patch('app.core.contexts.inject_role_permissions', return_value=_allow_all_permissions()):
        response = client.get(
            '/agro/magazyn/inwentaryzacja-produkcji/historia/XYZ?linia=AGRO',
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert '/agro/magazyn/inwentaryzacja-produkcji?linia=AGRO' in response.headers['Location']
