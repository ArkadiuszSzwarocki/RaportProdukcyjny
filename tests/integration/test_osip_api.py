"""
Testy integracyjne dla tras HTTP/API Blueprintu OSIP.
"""
from unittest.mock import patch
import pytest


@pytest.fixture
def osip_logged_client(client):
    """Tworzy zalogowanego klienta z sesją w aplikacji."""
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'test_magazynier'
        sess['rola'] = 'magazynier'
        sess['subrole'] = 'OSIP'
    return client


def test_osip_warehouse_view_unauthenticated(client):
    """Próba wejścia bez zalogowania przekierowuje do /login (302)."""
    response = client.get('/osip/warehouse')
    assert response.status_code == 302
    assert '/login' in response.location


def test_osip_warehouse_view_authenticated(osip_logged_client):
    """Zalogowany użytkownik wchodzący na /osip/warehouse zostaje przekierowany do ujednoliconego widoku warehouse_v2 (zakladka=OSIP)."""
    response = osip_logged_client.get('/osip/warehouse', follow_redirects=True)
    assert response.status_code == 200
    assert "Wszystkie Magazyny" in response.get_data(as_text=True) or "OSIP" in response.get_data(as_text=True)


def test_osip_inventory_api(osip_logged_client):
    """Endpoint /osip/api/inventory zwraca dane surowców i wyrobów w formacie JSON."""
    mock_data = {
        "raw_materials": [{"id": 1, "nr_palety": "SUR-001", "nazwa": "Kukurydza", "ilosc_kg": 500, "lokalizacja": "OS01"}],
        "finished_goods": [],
        "total_raw": 1,
        "total_fg": 0
    }
    with patch('app.blueprints.osip.routes.warehouse_service.get_osip_inventory', return_value=mock_data):
        response = osip_logged_client.get('/osip/api/inventory', headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 200
        json_resp = response.get_json()
        assert json_resp["success"] is True
        assert json_resp["data"]["total_raw"] == 1


def test_osip_transfers_api_list(osip_logged_client):
    """Endpoint /osip/api/transfers zwraca listę zaktualizowanych transferów."""
    with patch('app.blueprints.osip.routes.transfer_service.get_transfers_list', return_value=[]):
        response = osip_logged_client.get('/osip/api/transfers', headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 200
        json_resp = response.get_json()
        assert json_resp["success"] is True
        assert "transfers" in json_resp


def test_osip_scan_receive_api(osip_logged_client):
    """Endpoint /osip/api/transfers/<id>/scan_receive przyjmuje paletę po kodzie."""
    mock_result = {
        "success": True,
        "message": "Przyjęto paletę SUR000001785221455251 do OS05",
        "item_id": 1,
        "location": "OS05",
        "received_count": 1,
        "total_count": 17,
        "completed": False
    }
    with patch('app.blueprints.osip.routes.transfer_service.receive_single_item', return_value=mock_result):
        response = osip_logged_client.post(
            '/osip/api/transfers/1/scan_receive',
            json={"pallet_code": "SUR000001785221455251", "target_location": "OS05"}
        )
        assert response.status_code == 200
        json_resp = response.get_json()
        assert json_resp["success"] is True
        assert json_resp["location"] == "OS05"
