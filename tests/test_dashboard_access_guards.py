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

    def test_role_without_production_permissions_falls_back_to_shared_warehouse(self, mock_is_active, client, mock_query_helper):
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'widz'
            sess['user_id'] = 5
            sess['username'] = 'widz'
            sess['rola'] = 'widz'
            sess['pracownik_id'] = 200

        # Production access is denied, but shared warehouses remain available after login.
        response = client.get('/')
        assert response.status_code == 302
        assert 'sekcja=Magazyn' in response.headers['Location']


@pytest.fixture(autouse=True)
def explicit_worker_page_policy():
    # Route tests must not inherit the operator's saved UI permission settings.
    from pathlib import Path
    import json
    policy = json.loads((Path(__file__).parents[1] / 'config/role_permissions.json').read_text(encoding='utf-8'))
    policy.setdefault('psd.zasyp', {})['pracownik'] = {'access': True, 'readonly': False}
    policy.setdefault('dashboard', {})['pracownik'] = {'access': False, 'readonly': False}
    # Access checks do not require production records or a reachable database.
    def overview(day, line, role, **kwargs):
        return {'halls_to_fetch': [], 'halls_data': {}, 'shift_notes': [],
                'dzisiaj': day, 'dzisiaj_fmt': day.strftime('%d.%m.%Y'),
                'linia': line, 'sekcja': 'Dashboard', 'rola': role,
                'data_od': None, 'data_do': None, 'agro_measurements': {}}

    with patch('app.blueprints.main.index_data.build_production_overview_context', side_effect=overview), patch(
            'app.core.contexts._get_role_permissions', return_value=policy), patch(
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
