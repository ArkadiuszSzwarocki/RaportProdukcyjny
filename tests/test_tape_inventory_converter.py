import pytest
from unittest.mock import MagicMock, patch
from app.services.inwentaryzacja_service import InwentaryzacjaService


def test_calculate_tape_pieces_basic():
    assert InwentaryzacjaService.calculate_tape_pieces(500, 0.150) == 3333
    assert InwentaryzacjaService.calculate_tape_pieces('500', '0,150') == 3333
    assert InwentaryzacjaService.calculate_tape_pieces(0, 0.150) == 0


def test_calculate_tape_pieces_invalid():
    with pytest.raises(ValueError):
        InwentaryzacjaService.calculate_tape_pieces(500, 0)
    with pytest.raises(ValueError):
        InwentaryzacjaService.calculate_tape_pieces(500, -0.1)
    with pytest.raises(ValueError):
        InwentaryzacjaService.calculate_tape_pieces(-10, 0.15)


def test_get_tape_conversions_merges_saved_and_existing():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def fake_fetchall():
        sql = str(mock_cursor.execute.call_args[0][0])
        if 'FROM magazyn_tasmy_przeliczniki' in sql:
            return [{'nazwa': 'Fiolet', 'waga_worka_kg': 0.15, 'updated_by': 'szwarark', 'updated_at': None}]
        if 'FROM magazyn_opakowania' in sql:
            return [{'nazwa': 'Fiolet'}, {'nazwa': 'MaxFutter Niebieski'}]
        return []

    mock_cursor.fetchall.side_effect = fake_fetchall

    with patch('app.services.inwentaryzacja_service.get_db_connection', return_value=mock_conn):
        items = InwentaryzacjaService.get_tape_conversions()

    assert len(items) == 2
    by_name = {i['nazwa']: i for i in items}
    assert by_name['Fiolet']['waga_worka_kg'] == 0.15
    assert by_name['MaxFutter Niebieski']['waga_worka_kg'] is None


def test_save_tape_conversions_bulk_upsert_and_delete():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('app.services.inwentaryzacja_service.get_db_connection', return_value=mock_conn):
        ok, msg = InwentaryzacjaService.save_tape_conversions_bulk(
            [
                {'nazwa': 'Fiolet', 'waga_worka_kg': '0,150'},
                {'nazwa': 'Biała', 'waga_worka_kg': ''},
            ],
            user_login='szwarark',
        )

    assert ok is True
    assert mock_conn.commit.called
    executed = [str(c[0][0]) for c in mock_cursor.execute.call_args_list]
    assert any('INSERT INTO magazyn_tasmy_przeliczniki' in sql for sql in executed)
    assert any('DELETE FROM magazyn_tasmy_przeliczniki' in sql for sql in executed)


def test_save_tape_conversions_bulk_rejects_non_positive():
    ok, msg = InwentaryzacjaService.save_tape_conversions_bulk(
        [{'nazwa': 'Fiolet', 'waga_worka_kg': 0}],
        user_login='szwarark',
    )
    assert ok is False
    assert 'większa od 0' in msg


def test_api_tasmy_przeliczniki_get_and_post(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'magazynier'
        sess['login'] = 'szwarark'

    sample_items = [
        {'nazwa': 'Fiolet', 'waga_worka_kg': 0.15, 'updated_by': 'szwarark', 'updated_at': ''},
        {'nazwa': 'Biała', 'waga_worka_kg': None, 'updated_by': '', 'updated_at': ''},
    ]

    with patch.object(InwentaryzacjaService, 'get_tape_conversions', return_value=sample_items):
        resp = client.get('/magazyn/inwentaryzacja/api/tasmy-przeliczniki')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['map'] == {'fiolet': 0.15}

    with patch.object(InwentaryzacjaService, 'save_tape_conversions_bulk', return_value=(True, 'Zapisano')) as mock_save, \
         patch.object(InwentaryzacjaService, 'get_tape_conversions', return_value=sample_items):
        resp2 = client.post(
            '/magazyn/inwentaryzacja/api/tasmy-przeliczniki',
            json={'nazwa': 'Fiolet', 'waga_worka_kg': 0.15},
            content_type='application/json',
        )
    assert resp2.status_code == 200
    assert resp2.get_json()['success'] is True
    mock_save.assert_called_once_with([{'nazwa': 'Fiolet', 'waga_worka_kg': 0.15}], user_login='szwarark')


def test_save_split_tape_rolls_creates_separate_roll_entries():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    with patch('app.services.inwentaryzacja_service.get_db_connection', return_value=mock_conn):
        ok, msg, created_ssccs = InwentaryzacjaService.save_split_tape_rolls(
            sesja_id=170,
            paleta_id=42,
            typ_palety='opakowanie',
            nazwa='Fiolet',
            lokalizacja='R060405',
            nr_partii='BRAK',
            waga_systemowa=5000,
            rolls_szt=[1200, 1133, 1000],
            user_login='szwarark',
            linia='PSD',
            nr_palety='OPK080520268220711005',
        )

    assert ok is True
    assert '3 rolek' in msg
    assert '3333 szt' in msg
    assert len(created_ssccs) == 2
    assert all(code.startswith('OPK000') for code in created_ssccs)
    assert len(set(created_ssccs)) == 2
    assert mock_conn.commit.called
    inserts = [c for c in mock_cursor.execute.call_args_list if 'INSERT INTO magazyn_inwentaryzacja_wpisy' in str(c[0][0])]
    assert len(inserts) == 3


def test_api_zapisz_wpis_delegates_split_rolls(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'magazynier'
        sess['login'] = 'szwarark'

    with patch.object(
        InwentaryzacjaService,
        'save_split_tape_rolls',
        return_value=(True, 'Zapisano 2 rolek (razem 3333 szt)', ['OPK000001']),
    ) as mock_split:
        resp = client.post(
            '/magazyn/inwentaryzacja/api/zapisz-wpis',
            json={
                'sesja_id': 170,
                'paleta_id': 42,
                'nr_palety': 'OPK080520268220711005',
                'typ_palety': 'opakowanie',
                'nazwa': 'Fiolet',
                'lokalizacja': 'R060405',
                'waga_systemowa': 5000,
                'waga_faktyczna': 1667,
                'rolls_szt': [1667, 1666],
                'jednostka': 'szt',
            },
            content_type='application/json',
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['created_ssccs'] == ['OPK000001']
    mock_split.assert_called_once()


def test_scanner_split_tape_rolls_direct_endpoint(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'magazynier'
        sess['login'] = 'szwarark'

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {
        'id': 42,
        'nr_palety': 'OPK080520268220711005',
        'nazwa': 'Fiolet',
        'stan_magazynowy': 5277.0,
        'lokalizacja': 'R060405',
        'nr_partii': 'BRAK',
        'data_produkcji': None,
        'data_przydatnosci': None,
        'typ_opakowania': 'Taśma',
        'linia': 'PSD',
    }
    mock_cursor.lastrowid = 501

    with patch('app.db.get_db_connection', return_value=mock_conn), \
         patch('app.services.warehouse_history.movement_recorder.MovementRecorder.record_movement', return_value=True) as mock_rec, \
         patch.object(InwentaryzacjaService, 'save_tape_conversions_bulk', return_value=(True, 'OK')):
        resp = client.post(
            '/agro/scanner/split-tape-rolls',
            json={
                'pallet_id': 42,
                'nr_palety': 'OPK080520268220711005',
                'rolls_szt': [1200, 1133, 1000],
                'bag_weight_kg': 0.15,
                'save_bag_weight': True,
                'print_labels': False,
            },
            content_type='application/json',
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert len(data['rolls']) == 3
    assert data['rolls'][0]['stan_magazynowy'] == 1200
    assert data['rolls'][0]['is_source'] is True
    assert data['rolls'][1]['nr_palety'].startswith('OPK000')
    assert data['rolls'][2]['nr_palety'].startswith('OPK000')
    assert mock_conn.commit.called
    assert mock_rec.call_count == 3



