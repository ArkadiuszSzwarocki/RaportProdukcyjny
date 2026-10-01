"""Dashboard failures use the shared error response without exposing internals."""

from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('accept', ['text/html', 'application/json'])
def test_dashboard_error_keeps_exception_details_out_of_response(client, app, monkeypatch, accept):
    app.debug = False
    details = "Table 'private_database.szarze_agro' missing at C:/private/server.py"
    monkeypatch.setattr(
        'app.blueprints.main.build_dashboard_halls_context',
        Mock(side_effect=RuntimeError(details)),
    )
    with client.session_transaction() as session:
        session.update(zalogowany=True, user_id=1, login='admin', rola='admin', grupa='ALL')

    response = client.get('/?sekcja=Zasyp&linia=AGRO', headers={'Accept': accept})

    assert response.status_code == 500
    body = response.get_data(as_text=True)
    assert 'ERR-' in body
    for internal_detail in (details, 'private_database', 'szarze_agro', 'C:/private', 'Traceback', 'RuntimeError'):
        assert internal_detail not in body
