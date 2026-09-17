import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.services.warehouse_pallet_service import WarehousePalletService


def test_edytuj_palete_magazyn_success():
    """Test editing pallet weight for pallet already in magazyn_palety."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Setup magazyn row: (id, paleta_workowanie_id, plan_id, waga_netto, nr_palety, tara)
    mock_cursor.fetchone.return_value = (755, 768, 287, 1.0, 'AGR000001789365664871', 25.0)

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'

    with app.test_request_context():
        with patch('app.services.warehouse_pallet_service.get_db_connection', return_value=mock_conn):
            result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
                paleta_id=755,
                linia='AGRO',
                waga_palety='1000',
                user_login='masteradmin',
                update_paleta_workowanie=None,
                is_ajax=True,
                safe_return_url='/dashboard'
            )

    assert status_code == 200
    assert result['success'] is True
    assert '1000' in result['message']
    assert mock_conn.commit.called

    # Verify executed statements
    executed_sqls = [str(call[0][0]) for call in mock_cursor.execute.call_args_list]
    assert any('UPDATE magazyn_palety_agro SET waga_netto=%s, waga_brutto=%s WHERE id=%s' in sql for sql in executed_sqls)
    assert any('UPDATE palety_agro SET waga_potwierdzona=%s, waga=%s WHERE id=%s' in sql for sql in executed_sqls)
    assert any('UPDATE plan_produkcji_agro' in sql for sql in executed_sqls)
    assert any('INSERT INTO palety_historia' in sql for sql in executed_sqls)


def test_edytuj_palete_cross_line_fallback():
    """Test editing AGRO pallet when linia is erroneously provided as 'PSD'."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def fake_execute(sql, params=None):
        pass

    def fake_fetchone():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'magazyn_palety ' in sql or 'palety_workowanie' in sql:
                # PSD table: not found
                return None
            if 'magazyn_palety_agro' in sql:
                return (755, 768, 287, 1.0, 'AGR000001789365664871', 25.0)
        return None

    mock_cursor.execute.side_effect = fake_execute
    mock_cursor.fetchone.side_effect = fake_fetchone

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'

    with app.test_request_context():
        with patch('app.services.warehouse_pallet_service.get_db_connection', return_value=mock_conn):
            result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
                paleta_id=755,
                linia='PSD',  # Provided as PSD, but pallet is AGRO
                waga_palety='1000',
                user_login='masteradmin',
                update_paleta_workowanie=None,
                is_ajax=True,
                safe_return_url='/dashboard'
            )

    assert status_code == 200
    assert result['success'] is True
    assert mock_conn.commit.called


def test_edytuj_palete_unconfirmed_buffer():
    """Test editing unconfirmed pallet in buffer (palety_workowanie)."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def fake_fetchone():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'magazyn_palety' in sql:
                return None
            if 'palety_workowanie' in sql:
                return (123, 50, 950.0, None, 'oczekuje', 'PSD000123')
        return None

    mock_cursor.fetchone.side_effect = fake_fetchone

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'

    with app.test_request_context():
        with patch('app.services.warehouse_pallet_service.get_db_connection', return_value=mock_conn):
            result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
                paleta_id=123,
                linia='PSD',
                waga_palety='1000',
                user_login='masteradmin',
                update_paleta_workowanie=None,
                is_ajax=True,
                safe_return_url='/dashboard'
            )

    assert status_code == 200
    assert result['success'] is True
    executed_sqls = [str(call[0][0]) for call in mock_cursor.execute.call_args_list]
    assert any('UPDATE palety_workowanie SET waga=%s WHERE id=%s' in sql for sql in executed_sqls)
    assert any('UPDATE plan_produkcji' in sql for sql in executed_sqls)


def test_edytuj_palete_not_found():
    """Test editing non-existent pallet."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'

    with app.test_request_context():
        with patch('app.services.warehouse_pallet_service.get_db_connection', return_value=mock_conn):
            result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
                paleta_id=999999,
                linia='PSD',
                waga_palety='1000',
                user_login='masteradmin',
                update_paleta_workowanie=None,
                is_ajax=True,
                safe_return_url='/dashboard'
            )

    assert status_code == 404
    assert result['success'] is False


def test_api_edytuj_palete_ajax_endpoint_without_id_in_url(client):
    """Test POST /api/edytuj_palete_ajax without id in url, id in json body."""
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'masteradmin'
        sess['login'] = 'masteradmin'

    with patch.object(WarehousePalletService, 'edytuj_palete') as mock_edit:
        mock_edit.return_value = ({'success': True, 'message': 'Paleta zaktualizowana (waga=1000 kg)'}, 200, None)
        response = client.post(
            '/api/edytuj_palete_ajax',
            json={'id': 755, 'waga': '1000', 'linia': 'AGRO'},
            content_type='application/json'
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    mock_edit.assert_called_once()
    args, kwargs = mock_edit.call_args
    assert args[0] == 755
    assert args[1] == 'AGRO'
    assert args[2] == '1000'


def test_api_edytuj_palete_ajax_endpoint_with_id_in_url(client):
    """Test POST /api/edytuj_palete_ajax/<paleta_id> with id in url."""
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'
        sess['login'] = 'admin'

    with patch.object(WarehousePalletService, 'edytuj_palete') as mock_edit:
        mock_edit.return_value = ({'success': True, 'message': 'Paleta zaktualizowana (waga=1000 kg)'}, 200, None)
        response = client.post(
            '/api/edytuj_palete_ajax/755',
            json={'waga': '1000'},
            content_type='application/json'
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    mock_edit.assert_called_once()
    args, kwargs = mock_edit.call_args
    assert args[0] == 755
    assert args[2] == '1000'
