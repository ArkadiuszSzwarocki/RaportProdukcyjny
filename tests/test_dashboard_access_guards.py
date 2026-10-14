# cspell:words autouse
import pytest
from unittest.mock import patch, MagicMock

@patch('app.core.middleware.is_session_active', return_value=True)
class TestDashboardAccessGuards:
    """Explicit tests for dashboard role-based visibility restrictions."""

    def test_admin_has_full_access_to_dashboard(self, mock_is_active, client, mock_query_helper):
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'admin'
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['rola'] = 'admin'
            sess['pracownik_id'] = 1

        response = client.get('/')
        assert response.status_code == 200

    def test_lider_has_full_access_to_dashboard(self, mock_is_active, client, mock_query_helper):
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'lider'
            sess['user_id'] = 2
            sess['username'] = 'lider'
            sess['rola'] = 'lider'
            sess['pracownik_id'] = 50

        response = client.get('/')
        assert response.status_code == 200

    def test_planista_has_access_to_dashboard(self, mock_is_active, client, mock_query_helper):
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'planista'
            sess['user_id'] = 3
            sess['username'] = 'planista'
            sess['rola'] = 'planista'
            sess['pracownik_id'] = 51

        response = client.get('/')
        assert response.status_code == 200

    def test_pracownik_is_redirected_from_dashboard_to_first_allowed_section(self, mock_is_active, client, mock_query_helper):
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'pracownik'
            sess['user_id'] = 4
            sess['username'] = 'pracownik'
            sess['rola'] = 'pracownik'
            sess['pracownik_id'] = 100

        # Pracownik should be redirected seamlessly to Zasyp (first allowed page)
        response = client.get('/')
        assert response.status_code == 302
        assert 'sekcja=Zasyp' in response.headers['Location']

    def test_unauthorized_role_without_any_permissions_gets_403(self, mock_is_active, client, mock_query_helper):
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'widz'
            sess['user_id'] = 5
            sess['username'] = 'widz'
            sess['rola'] = 'widz'
            sess['pracownik_id'] = 200

        # widz has access=false to everything, should get a 403 Forbidden page
        response = client.get('/')
        assert response.status_code == 403


@pytest.fixture(autouse=True)
def explicit_worker_page_policy():
    # Route tests must not inherit the operator's saved UI permission settings.
    from pathlib import Path
    import json
    policy = json.loads((Path(__file__).parents[1] / 'config/role_permissions.json').read_text(encoding='utf-8'))
    policy.setdefault('psd.zasyp', {})['pracownik'] = {'access': True, 'readonly': False}
    policy.setdefault('dashboard', {})['pracownik'] = {'access': False, 'readonly': False}
    with patch('app.core.contexts._get_role_permissions', return_value=policy), patch(
            'app.repositories.user_permission_override_repository.user_permission_override_repository.get_user_override', return_value=None):
        yield


@pytest.mark.parametrize('hall', ['PSD', 'AGRO'])
def test_root_redirect_uses_assigned_hall_without_selected_view(client, hall):
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='test-navigation', rola='pracownik', grupa=hall)
    helpers = {'role_has_access': lambda page: page == hall.lower() + '.zasyp',
               'role_is_readonly': lambda page: False}
    with patch('app.core.contexts.inject_role_permissions', return_value=helpers), patch(
            'app.blueprints.main.build_dashboard_halls_context') as fetch_dashboard:
        response = client.get('/')
    assert response.status_code == 302
    assert 'sekcja=Zasyp' in response.headers['Location']
    assert 'linia=' + hall in response.headers['Location']
    fetch_dashboard.assert_not_called()
