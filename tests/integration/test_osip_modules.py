"""
Testy integracyjne dla nowych modułów magazynu OSIP:
- Suma surowców
- Przyjęcie dostawy OSIP
- Oczekujące przyjęcia OSIP
- Podział palety OSIP
- Miksowanie palet OSIP
"""
import pytest
from unittest.mock import patch


@pytest.fixture
def osip_admin_client(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 1
        sess['login'] = 'admin'
        sess['username'] = 'admin'
        sess['rola'] = 'admin'
        sess['subrole'] = 'OSIP'
    return client


def test_osip_suma_surowcow_view(osip_admin_client):
    """Widok sumy surowców OSIP renderuje się prawidłowo."""
    mock_grouped = [
        {
            'nazwa': 'Mączka sojowa',
            'total_kg': 1500.0,
            'pallet_count': 2,
            'pallets': [
                {'id': 101, 'nr_palety': 'PL-101', 'stan_magazynowy': 750.0, 'nr_partii': 'P01', 'lokalizacja': 'A01', 'typ_opakowania': 'Worek', 'data_przydatnosci': '2027-01-01'},
                {'id': 102, 'nr_palety': 'PL-102', 'stan_magazynowy': 750.0, 'nr_partii': 'P01', 'lokalizacja': 'A02', 'typ_opakowania': 'Worek', 'data_przydatnosci': '2027-01-01'}
            ],
            'batches': ['P01'],
            'locations': ['A01', 'A02']
        }
    ]
    with patch('app.blueprints.osip.routes.warehouse_service.get_osip_grouped_inventory', return_value=mock_grouped):
        res = osip_admin_client.get('/osip/suma-surowcow')
        assert res.status_code == 200
        text = res.get_data(as_text=True)
        assert 'Suma Surowców – Magazyn OSIP' in text
        assert 'Mączka sojowa' in text
        assert '1 500.00 kg' in text or '1500' in text


def test_osip_reception_view(osip_admin_client):
    """Widok przyjęcia zewnętrznego dostawy dla linii OSIP."""
    res = osip_admin_client.get('/magazyn-dostawy/przyjecie?linia=OSIP')
    assert res.status_code == 200


def test_osip_reception_form_locations(osip_admin_client):
    """Formularz przyjęcia dostawy dla OSIP zawiera lokalizację buforową BFOS."""
    res = osip_admin_client.get('/magazyn-dostawy/przyjecie/nowe?linia=OSIP')
    assert res.status_code == 200
    text = res.get_data(as_text=True)
    assert 'BFOS' in text


def test_osip_oczekujace_view(osip_admin_client):
    """Widok oczekujących przyjęć dla linii OSIP."""
    res = osip_admin_client.get('/magazyn-dostawy/oczekujace?linia=OSIP')
    assert res.status_code == 200


def test_osip_podzial_palety_view(osip_admin_client):
    """Widok podziału palet renderuje się z linią OSIP."""
    res = osip_admin_client.get('/magazyn-dostawy/podzial-palety?linia=OSIP')
    assert res.status_code == 200


def test_osip_mixowanie_view(osip_admin_client):
    """Widok mixowania palet renderuje się z linią OSIP."""
    res = osip_admin_client.get('/magazyn-dostawy/mixowanie?linia=OSIP')
    assert res.status_code == 200


def test_centrala_osip_direct_move_blocked():
    """Bezpośrednie przenoszenie palet między Centralą a OSIP bez transferu jest blokowane."""
    from app.utils.location_validator import validate_centrala_osip_move
    ok, msg = validate_centrala_osip_move(
        source_location='MS01',
        target_location='A05',
        pallet_id=999999,
        nr_palety='TEST_PALLET_NO_TRF'
    )
    assert ok is False
    assert 'zablokowane' in msg

    ok2, msg2 = validate_centrala_osip_move(
        source_location='A12',
        target_location='MP01',
        pallet_id=999999,
        nr_palety='TEST_PALLET_NO_TRF'
    )
    assert ok2 is False
    assert 'zablokowane' in msg2


def test_within_warehouse_moves_allowed():
    """Przenoszenie palet wewnątrz Centrali lub wewnątrz OSIP jest dozwolone."""
    from app.utils.location_validator import validate_centrala_osip_move
    ok, msg = validate_centrala_osip_move(
        source_location='MS01',
        target_location='R040101',
        pallet_id=999999,
        nr_palety='TEST_PALLET'
    )
    assert ok is True
    assert msg is None

    ok2, msg2 = validate_centrala_osip_move(
        source_location='A01',
        target_location='A05',
        pallet_id=999999,
        nr_palety='TEST_PALLET'
    )
    assert ok2 is True
    assert msg2 is None
