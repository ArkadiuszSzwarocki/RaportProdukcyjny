from unittest.mock import MagicMock, patch

import pytest


def _set_session_role(client, role):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = role
        sess['login'] = f'{role}_user'
        sess['grupa'] = 'ALL'


@pytest.mark.parametrize('linia', ['AGRO', 'PSD'])
@pytest.mark.parametrize('role', ['lider', 'admin'])
def test_confirm_delete_palete_page_allows_lider_and_admin(client, role, linia):
    _set_session_role(client, role)

    response = client.get(f'/confirm_delete_palete_page/123?linia={linia}')

    assert response.status_code == 200


def test_confirm_delete_palete_page_denies_produkcja(client):
    _set_session_role(client, 'produkcja')

    response = client.get('/confirm_delete_palete_page/123?linia=AGRO')

    assert response.status_code == 403


@pytest.mark.parametrize('linia', ['AGRO', 'PSD'])
@pytest.mark.parametrize('role', ['lider', 'admin'])
def test_usun_palete_allows_lider_and_admin(client, role, linia):
    _set_session_role(client, role)

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = (77,)

    with patch('app.blueprints.routes_warehouse_management.get_db_connection', return_value=conn):
        response = client.post('/usun_palete/5', data={'linia': linia}, follow_redirects=False)

    assert response.status_code == 302
    conn.commit.assert_called_once()


def test_usun_palete_denies_produkcja(client):
    _set_session_role(client, 'produkcja')

    response = client.post('/usun_palete/5', data={'linia': 'AGRO'}, follow_redirects=False)

    assert response.status_code == 403


@pytest.mark.parametrize('linia', ['AGRO', 'PSD'])
@pytest.mark.parametrize('role', ['produkcja', 'lider', 'admin'])
def test_usun_palete_ajax_allows_expected_roles(client, role, linia):
    _set_session_role(client, role)

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = None

    with patch('app.blueprints.routes_warehouse_management.get_db_connection', return_value=conn):
        response = client.post('/api/usun_palete_ajax', json={'id': 5, 'linia': linia})

    assert response.status_code == 404


def test_usun_palete_ajax_denies_pracownik(client):
    _set_session_role(client, 'pracownik')

    conn = MagicMock()
    with patch('app.blueprints.routes_warehouse_management.get_db_connection', return_value=conn):
        response = client.post('/api/usun_palete_ajax', json={'id': 5, 'linia': 'PSD'})

    assert response.status_code == 403
    conn.cursor.assert_not_called()
