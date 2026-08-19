import pytest
import json
from unittest.mock import MagicMock, patch
from app.core.factory import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    with app.test_client() as client:
        yield client

def test_available_pallets_fifo_order_and_badges(client):
    """Test sprawdza czy API /api/dostepne-palety poprawnie sortuje wg FIFO i oznacza pierwszą paletę."""
    fake_pallets = [
        # Tańsza / nowsza data prod
        {
            'id': 201,
            'nr_palety': 'PL-HYDRO-02',
            'nazwa': 'Hydroksypropylometyloceluloza',
            'stan_magazynowy': 500,
            'lokalizacja': 'R010203',
            'nr_partii': 'LOT-2026-B',
            'data_produkcji': '2026-05-10',
            'data_przydatnosci': '2027-05-10',
            'type': 'surowiec'
        },
        # Najstarsza data - 1. do zużycia (FIFO)
        {
            'id': 101,
            'nr_palety': 'PL-HYDRO-01',
            'nazwa': 'Hydroksypropylometyloceluloza',
            'stan_magazynowy': 750,
            'lokalizacja': 'R010101',
            'nr_partii': 'LOT-2026-A',
            'data_produkcji': '2026-01-15',
            'data_przydatnosci': '2027-01-15',
            'type': 'surowiec'
        },
        # Trzecia paleta
        {
            'id': 301,
            'nr_palety': 'PL-HYDRO-03',
            'nazwa': 'Hydroksypropylometyloceluloza',
            'stan_magazynowy': 1000,
            'lokalizacja': 'R020101',
            'nr_partii': 'LOT-2026-C',
            'data_produkcji': '2026-08-01',
            'data_przydatnosci': '2027-08-01',
            'type': 'surowiec'
        }
    ]

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def fake_fetchall():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'magazyn_surowce' in sql:
                return fake_pallets.copy()
        return []

    mock_cursor.fetchall.side_effect = fake_fetchall

    with patch('app.blueprints.magazyn_dostawy.routes.pallets.get_db_connection', return_value=mock_conn):
        res = client.get('/magazyn-dostawy/api/dostepne-palety?linia=PSD&prefix=Hydro')
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        pallets = data['pallets']
        assert len(pallets) == 3

        # Sprawdź czy najstarsza paleta (LOT-2026-A) jest na 1. miejscu
        first = pallets[0]
        assert first['nr_palety'] == 'PL-HYDRO-01'
        assert first['is_first_fifo'] is True
        assert first['fifo_index'] == 1
        assert '⚡ 1. DO ZUŻYCIA' in first['fifo_badge']

        # Sprawdź drugą paletę
        second = pallets[1]
        assert second['nr_palety'] == 'PL-HYDRO-02'
        assert second['is_first_fifo'] is False
        assert second['fifo_index'] == 2

        # Sprawdź trzecią paletę
        third = pallets[2]
        assert third['nr_palety'] == 'PL-HYDRO-03'
        assert third['is_first_fifo'] is False
        assert third['fifo_index'] == 3

def test_available_pallets_multiple_pallets_same_earliest_date(client):
    """Test sprawdza czy wszystkie palety z tą samą najwcześniejszą datą są oznaczone jako 1. DO ZUŻYCIA."""
    fake_pallets = [
        # Dwie palety z tą samą najwcześniejszą datą
        {
            'id': 101,
            'nr_palety': 'PL-HYDRO-01',
            'nazwa': 'Hydro',
            'stan_magazynowy': 1000,
            'lokalizacja': 'R010102',
            'nr_partii': 'LOT-2026-A',
            'data_produkcji': '2026-04-30',
            'data_przydatnosci': '2027-04-30',
            'type': 'surowiec'
        },
        {
            'id': 102,
            'nr_palety': 'PL-HYDRO-02',
            'nazwa': 'Hydro',
            'stan_magazynowy': 1000,
            'lokalizacja': 'R010202',
            'nr_partii': 'LOT-2026-A',
            'data_produkcji': '2026-04-30',
            'data_przydatnosci': '2027-04-30',
            'type': 'surowiec'
        },
        # Paleta z późniejszą datą
        {
            'id': 201,
            'nr_palety': 'PL-HYDRO-03',
            'nazwa': 'Hydro',
            'stan_magazynowy': 1000,
            'lokalizacja': 'R020303',
            'nr_partii': 'LOT-2026-B',
            'data_produkcji': '2026-05-05',
            'data_przydatnosci': '2028-05-05',
            'type': 'surowiec'
        }
    ]

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def fake_fetchall():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'magazyn_surowce' in sql:
                return fake_pallets.copy()
        return []

    mock_cursor.fetchall.side_effect = fake_fetchall

    with patch('app.blueprints.magazyn_dostawy.routes.pallets.get_db_connection', return_value=mock_conn):
        res = client.get('/magazyn-dostawy/api/dostepne-palety?linia=PSD&prefix=Hydro')
        assert res.status_code == 200
        data = res.get_json()
        pallets = data['pallets']
        assert len(pallets) == 3

        # Obie pierwsze palety muszą mieć is_first_fifo = True
        assert pallets[0]['is_first_fifo'] is True
        assert pallets[0]['fifo_badge'] == '⚡ 1. DO ZUŻYCIA (FIFO)'

        assert pallets[1]['is_first_fifo'] is True
        assert pallets[1]['fifo_badge'] == '⚡ 1. DO ZUŻYCIA (FIFO)'

        # Trzecia paleta ma późniejszą datę
        assert pallets[2]['is_first_fifo'] is False
        assert pallets[2]['fifo_batch_num'] == 2
