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
