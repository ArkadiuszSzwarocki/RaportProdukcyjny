import pytest
from unittest.mock import MagicMock, patch
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService

def test_accept_production_pallet_agro_crossline_auto_detection():
    """Test sprawdza czy AcceptanceService automatycznie wykrywa linię AGRO i przyjmuje paletę nawet jeśli linia='PSD'."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    fake_agro_pallet = {
        'id': 643,
        'plan_id': 257,
        'nr_palety': 'AGR000001787139218902',
        'waga': 1000.0,
        'waga_brutto': 1025.0,
        'tara': 25.0,
        'status': 'do_przyjecia',
        'produkt_nazwa': 'AGRO MILK TOP',
        'produkt': 'AGRO MILK TOP',
        'data_planu': '2026-08-19'
    }

    def fake_execute(sql, params=None):
        pass

    def fake_fetchone():
        # Zwróć dane palety dla zapytania palety_agro
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'palety_agro' in sql:
                return fake_agro_pallet
            if 'palety_workowanie' in sql:
                return None
            if 'SELECT id FROM magazyn_palety_agro' in sql:
                return None
            if 'plan_produkcji_agro' in sql:
                return {'status': 'w_toku'}
        return None

    mock_cursor.execute.side_effect = fake_execute
    mock_cursor.fetchone.side_effect = fake_fetchone

    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection', return_value=mock_conn):
        # Wywołanie z domyślnym linia='PSD'
        ok, msg = AcceptanceService.accept_production_pallet(
            pallet_id=643,
            lokalizacja='MGW01',
            linia='PSD', # Błędna linia przesłana z frontendu
            login='magazynier_test',
            confirmed_weight=1000.0
        )

        assert ok is True
        assert "została przyjęta" in msg
        mock_conn.commit.assert_called()

def test_accept_production_pallet_by_nr_palety():
    """Test sprawdza czy można przyjąć paletę podając numer palety AGR..."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    fake_agro_pallet = {
        'id': 643,
        'plan_id': 257,
        'nr_palety': 'AGR000001787139218902',
        'waga': 1000.0,
        'waga_brutto': 1025.0,
        'tara': 25.0,
        'status': 'do_przyjecia',
        'produkt_nazwa': 'AGRO MILK TOP',
        'produkt': 'AGRO MILK TOP',
        'data_planu': '2026-08-19'
    }

    def fake_fetchone():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'palety_agro' in sql:
                return fake_agro_pallet
            if 'SELECT id FROM magazyn_palety_agro' in sql:
                return None
            if 'plan_produkcji_agro' in sql:
                return {'status': 'w_toku'}
        return None

    mock_cursor.fetchone.side_effect = fake_fetchone

    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection', return_value=mock_conn):
        ok, msg = AcceptanceService.accept_production_pallet(
            pallet_id='AGR000001787139218902',
            lokalizacja='MGW01',
            linia='PSD',
            login='magazynier_test',
            confirmed_weight=1000.0
        )

        assert ok is True
        assert "została przyjęta" in msg
