"""Laboratory login lands on the permitted dashboard rather than the scanner."""
from unittest.mock import patch

import pytest

from app.blueprints.auth.base import get_user_redirect_target


@pytest.mark.parametrize('role', ['laborant', 'laboratorium', '6', ' Laborant '])
@pytest.mark.parametrize('group,line', [('AGRO', 'AGRO'), ('PSD', 'PSD'), ('ALL', 'AGRO'), ('', 'AGRO')])
def test_laboratory_target_respects_hall(role, group, line):
    assert get_user_redirect_target(role, group) == '/?linia=' + line


def test_existing_special_targets_are_preserved():
    assert get_user_redirect_target('magazynier', 'OSIP') == '/osip/transfers'
    assert get_user_redirect_target('planista', 'ALL') == '/planista'
    assert get_user_redirect_target('masteradmin', 'ALL') == '/agro/scanner/ui'


def test_logged_in_laboratory_login_redirects_to_allowed_section(client):
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='test-laboratory', rola='laborant', grupa='AGRO')
    helpers = {'role_has_access': lambda key: key == 'agro.zasyp',
               'role_is_readonly': lambda key: True}
    with patch('app.core.contexts.inject_role_permissions', return_value=helpers), patch(
            'app.blueprints.main.build_dashboard_halls_context') as fetch_dashboard:
        response = client.get('/login')
        assert response.status_code == 302
        assert response.location == '/?linia=AGRO'
        landing = client.get(response.location)
    assert landing.status_code == 302
    assert 'sekcja=Zasyp' in landing.location
    assert 'linia=AGRO' in landing.location
    fetch_dashboard.assert_not_called()
