from unittest.mock import MagicMock, patch

def test_agro_staff_visibility_get(client):
    with patch('app.blueprints.production.support.get_db_connection') as mock_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.side_effect = [
            [(1, 'Jan Kowalski', 1), (2, 'Anna Nowak', 0)],  # staff rows
            []  # obsada rows
        ]

        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['rola'] = 'admin'

        response = client.get('/api/obsada/agro_staff_visibility', headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['success'] is True
        assert len(payload['staff']) == 2
        assert payload['staff'][0]['imie_nazwisko'] == 'Jan Kowalski'
        assert payload['staff'][0]['widoczny_agro'] is True
        assert payload['staff'][1]['widoczny_agro'] is False


def test_agro_staff_visibility_update(client):
    with patch('app.blueprints.production.support.get_db_connection') as mock_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['rola'] = 'admin'

        response = client.post('/api/obsada/agro_staff_visibility', json={'visible_ids': [1, 3]}, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['success'] is True
        mock_cursor.execute.assert_any_call("UPDATE pracownicy SET widoczny_agro = 0")


def test_agro_staff_visibility_update_with_assignments(client):
    with patch('app.blueprints.production.support.get_db_connection') as mock_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['rola'] = 'admin'

        payload = {
            'visible_ids': [1, 2],
            'assignments': {
                'Operator sterowni': [1],
                'Operator workowania': [2]
            },
            'date': '2026-08-21'
        }

        response = client.post('/api/obsada/agro_staff_visibility', json=payload, headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 200
        res = response.get_json()
        assert res['success'] is True
        mock_cursor.execute.assert_any_call(
            "DELETE FROM obsada_zmiany WHERE data_wpisu = %s AND UPPER(COALESCE(linia, '')) = 'AGRO' AND (sekcja = %s OR sekcja = %s)",
            ('2026-08-21', 'Operator sterowni', 'sterowni')
        )
        mock_cursor.execute.assert_any_call(
            "INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id, linia) VALUES (%s, %s, %s, 'AGRO')",
            ('2026-08-21', 'Operator sterowni', 1)
        )

