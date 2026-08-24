"""
Testy integracyjne dla widoku i tras API Wydań Zewnętrznych na Samochód (Załadunki ZZA/ZZL).
"""
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def logged_warehouse_client(client):
    """Tworzy zalogowanego klienta magazyniera w aplikacji."""
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'magazynier_test'
        sess['username'] = 'magazynier_test'
        sess['rola'] = 'magazynier'
    return client


def test_zaladunki_view_unauthenticated(client):
    """Niezalogowany użytkownik zostaje przekierowany do logowania (302)."""
    resp = client.get('/warehouse-v2/zaladunki')
    assert resp.status_code == 302
    assert '/login' in resp.location


def test_zaladunki_view_authenticated(logged_warehouse_client):
    """Zalogowany magazynier otrzymuje widok załadunków (200 OK) ze skanerem kodów."""
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.get_dispatches_history', return_value=[]):
        resp = logged_warehouse_client.get('/warehouse-v2/zaladunki?linia=AGRO')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Załadunki na Samochód" in html
        assert "palletScanInput" in html
        assert "Zeskanuj Paletę do Załadunku" in html


def test_api_lookup_pallet_missing_code(logged_warehouse_client):
    """Lookup bez kodu zwraca 400 Bad Request."""
    resp = logged_warehouse_client.post(
        '/warehouse-v2/api/zaladunki/lookup-pallet',
        json={'code': '', 'linia': 'AGRO'}
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert "Nie podano kodu" in data['message']


def test_api_lookup_pallet_not_found(logged_warehouse_client):
    """Lookup nieistniejącej palety zwraca 404 Not Found."""
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.lookup_pallet_for_dispatch', return_value=None):
        resp = logged_warehouse_client.post(
            '/warehouse-v2/api/zaladunki/lookup-pallet',
            json={'code': 'PAL-NIE-MA', 'linia': 'AGRO'}
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
        assert "Nie znaleziono aktywnej palety" in data['message']


def test_api_lookup_pallet_success(logged_warehouse_client):
    """Lookup istniejącej palety zwraca 200 OK ze strukturą palety."""
    mock_pallet = {
        'id': 10,
        'nr_palety': 'PAL-1001',
        'displayId': 'PAL-1001',
        'productName': 'Mączka Wapienna',
        'amount': 1000.0,
        'location': 'R010101',
        'batch': 'B2026-01',
        'type': 'Surowiec',
        'linia': 'AGRO'
    }
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.lookup_pallet_for_dispatch', return_value=mock_pallet):
        resp = logged_warehouse_client.post(
            '/warehouse-v2/api/zaladunki/lookup-pallet',
            json={'code': 'PAL-1001', 'linia': 'AGRO'}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['pallet']['productName'] == 'Mączka Wapienna'
        assert data['pallet']['amount'] == 1000.0


def test_api_dispatch_vehicle_success(logged_warehouse_client):
    """Rejestracja wyjazdu zwraca 200 OK przy poprawnych danych."""
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.dispatch_pallet_to_vehicle', return_value=(True, 'Załadunek zarejestrowany (ID #101).')):
        payload = {
            'nr_palety': 'PAL-1001',
            'nazwa_produktu': 'Mączka Wapienna',
            'typ_palety': 'Surowiec',
            'ilosc_kg': 1000.0,
            'nr_rejestracyjny': 'PO 12345',
            'kierowca': 'Piotr Nowak',
            'nr_dokumentu_wz': 'WZ/2026/01'
        }
        resp = logged_warehouse_client.post(
            '/warehouse-v2/api/zaladunki/dispatch',
            json=payload
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert "ID #101" in data['message']


def test_api_dispatch_history(logged_warehouse_client):
    """Pobranie historii wydań zewnętrznych zwraca listę rekordów oraz strukturę zgrupowaną po WZ."""
    mock_history = [
        {'id': 1, 'nr_dokumentu_wz': 'WZ/2026/10', 'nr_palety': 'PAL-01', 'nazwa_produktu': 'Kukurydza', 'ilosc_kg': 500, 'magazynier': 'magazynier_test'}
    ]
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.get_dispatches_history', return_value=mock_history):
        resp = logged_warehouse_client.get('/warehouse-v2/api/zaladunki/history')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['history']) == 1
        assert data['history'][0]['nr_palety'] == 'PAL-01'
        assert 'grouped' in data
        assert len(data['grouped']) == 1
        assert data['grouped'][0]['nr_dokumentu_wz'] == 'WZ/2026/10'
