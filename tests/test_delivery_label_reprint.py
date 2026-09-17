import pytest
import json
from unittest.mock import patch, MagicMock
from flask import Flask

@pytest.fixture
def app_client():
    from app.blueprints.magazyn_dostawy.base import magazyn_dostawy_bp
    app = Flask(__name__, template_folder='../../templates')
    app.config['SECRET_KEY'] = 'test-secret'
    app.config['TESTING'] = True
    app.register_blueprint(magazyn_dostawy_bp)
    
    with app.test_client() as client:
        with app.app_context():
            yield client

def test_dodruk_etykiet_missing_params(app_client):
    """Test validation when required parameters are missing."""
    res = app_client.post('/magazyn-dostawy/api/dodruk-etykiet', json={})
    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False

@patch('app.blueprints.magazyn_dostawy.routes.pallets.get_db_connection')
def test_dodruk_etykiet_printer_not_found(mock_db, app_client):
    """Test when printer ID is not found in database."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cursor
    mock_db.return_value = mock_conn

    res = app_client.post('/magazyn-dostawy/api/dodruk-etykiet', json={
        'nr_palety': 'SUR260819001',
        'printer_id': 999,
        'product_name': 'Cukier',
        'qty': 1000
    })
    assert res.status_code == 404
    data = res.get_json()
    assert data['success'] is False

@patch('app.blueprints.magazyn_dostawy.routes.pallets.get_db_connection')
@patch('threading.Thread')
def test_dodruk_etykiet_success(mock_thread, mock_db, app_client):
    """Test successful dodruk_etykiet dispatch."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {'id': 1, 'ip': '192.168.1.100', 'nazwa': 'Zebra_Magazyn'}
    mock_conn.cursor.return_value = mock_cursor
    mock_db.return_value = mock_conn

    res = app_client.post('/magazyn-dostawy/api/dodruk-etykiet', json={
        'nr_palety': 'SUR260819001',
        'printer_id': 1,
        'product_name': 'Cukier Krystaliczny',
        'nr_partii': 'LOT123',
        'data_produkcji': '2026-08-19',
        'data_przydatnosci': '2027-08-19',
        'qty': 1000,
        'p_type': 'surowiec'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'Wysłano 2 etykiety do drukarki' in data['message']
    assert mock_thread.called

@patch('app.blueprints.magazyn_dostawy.routes.pallets.get_db_connection')
@patch('threading.Thread')
def test_dodruk_etykiet_batch_success(mock_thread, mock_db, app_client):
    """Test successful batch dodruk_etykiet dispatch."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {'id': 1, 'ip': '192.168.1.100', 'nazwa': 'Zebra_Magazyn'}
    mock_conn.cursor.return_value = mock_cursor
    mock_db.return_value = mock_conn

    res = app_client.post('/magazyn-dostawy/api/dodruk-etykiet', json={
        'printer_id': 1,
        'copies': 2,
        'items': [
            {'nr_palety': 'SUR001', 'product_name': 'Cukier', 'qty': 1000, 'p_type': 'surowiec'},
            {'nr_palety': 'SUR002', 'product_name': 'Sól', 'qty': 500, 'p_type': 'surowiec'}
        ]
    })
    assert mock_thread.called

@patch('app.blueprints.magazyn_dostawy.routes.pallets.prepare_pallet_label_data')
@patch('app.blueprints.magazyn_dostawy.routes.pallets.get_db_connection')
@patch('threading.Thread')
def test_dodruk_etykiet_enriches_weight_from_db(mock_thread, mock_db, mock_prepare, app_client):
    """Test that when qty is missing or 0, dodruk_etykiet enriches weight and attributes from DB."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {'id': 1, 'ip': '192.168.1.100', 'nazwa': 'Zebra_Magazyn'}
    mock_conn.cursor.return_value = mock_cursor
    mock_db.return_value = mock_conn

    mock_prepare.return_value = {
        'id': 1474,
        'nrPalety': 'SUR000001785219620528',
        'nazwa': 'Makuch Lniany',
        'ilosc': 1000.0,
        'partia': '418B-25',
        'data_produkcji': '2025-11-18',
        'data_przydatnosci': '2026-11-18',
        'typ': 'SUROWIEC'
    }

    res = app_client.post('/magazyn-dostawy/api/dodruk-etykiet', json={
        'nr_palety': 'SUR000001785219620528',
        'printer_id': 1
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert mock_prepare.called

def test_prepare_pallet_label_data_sur_material():
    """Test that prepare_pallet_label_data correctly retrieves raw material with 1000kg from mock cursor."""
    from app.utils.pallet_label import prepare_pallet_label_data
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 1474,
        'nr_palety': 'SUR000001785219620528',
        'nazwa': 'Makuch Lniany',
        'stan_magazynowy': 1000.0,
        'nr_partii': '418B-25',
        'data_produkcji': '2025-11-18',
        'data_przydatnosci': '2026-11-18',
        'lokalizacja': 'MS01'
    }
    label = prepare_pallet_label_data(mock_cursor, 'SUR000001785219620528')
    assert label is not None
    assert label['nazwa'] == 'Makuch Lniany'
    assert label['ilosc'] == 1000.0
    assert label['partia'] == '418B-25'
    assert label['typ'] == 'SUROWIEC'
    assert label['jednostka'] == 'kg'

