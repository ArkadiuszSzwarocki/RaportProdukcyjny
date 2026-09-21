from unittest.mock import MagicMock, patch


def test_dodaj_dosypke_success(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'test_laborant'
        sess['rola'] = 'laborant'
        sess['pracownik_id'] = 12
        sess['user_id'] = 45
        sess['imie_nazwisko'] = 'Jan Laborant'

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Queries:
    # 1. plan query -> fetchone -> (301, 'MLECZNA PYCHA CZERWONA', '2026-09-21', 'w toku')
    # 2. szarza query -> fetchone -> (490, 1)
    # 3. _check_szarza_emptied -> fetchone -> None
    # 4. _get_allowed_dosypka_materials:
    #    - information_schema.TABLES -> fetchone -> (1,)
    #    - information_schema.COLUMNS -> fetchone -> (1,)
    # 5. SHOW COLUMNS pracownik_login -> fetchone -> (1,)
    mock_cursor.fetchone.side_effect = [
        (301, 'MLECZNA PYCHA CZERWONA', '2026-09-21', 'w toku'),  # 1. plan
        (490, 1),  # 2. szarza match
        None,  # 3. _check_szarza_emptied
        (1,),  # 4. table exists in information_schema
        (1,),  # 4. col exists in information_schema
        (1,),  # 5. SHOW COLUMNS pracownik_login
    ]
    mock_cursor.fetchall.return_value = [('Actisaf Drożdże Żywe',)]

    with patch('app.blueprints.production.dosypki.get_db_connection', return_value=mock_conn), \
         patch('app.blueprints.production.dosypki.sync_dosypka_notifications'):

        resp = client.post('/dodaj_dosypke', data={
            'plan_id': '301',
            'szarza_id': '490',
            'linia': 'AGRO',
            'nazwa_1': 'Actisaf Drożdże Żywe',
            'kg_1': '5.0',
        }, headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'Zapisano 1 pozycji dosypki' in data['message']

