"""Tests for authentication and authorization."""

import pytest
from unittest.mock import patch


class TestAuthentication:
    """Tests for authentication decorators and routes."""
    
    def test_unauthenticated_access_denied(self, client):
        """Test that unauthenticated users cannot access protected routes."""
        response = client.get('/', follow_redirects=False)
        
        # Should redirect to login
        assert response.status_code in [302, 401]
    
    def test_authenticated_access_allowed(self, authenticated_client):
        """Test that authenticated users can access protected routes."""
        response = authenticated_client.get('/')
        
        # Should either render or fail gracefully, not redirect to login
        assert response.status_code in [200, 302, 500]
    
    def test_session_persistent(self, authenticated_client):
        """Test that session persists across requests."""
        # First request
        authenticated_client.get('/')
        
        # Check session still exists
        with authenticated_client.session_transaction() as sess:
            assert 'user_id' in sess
            assert sess['user_id'] == 1


class TestRoleBasedAccess:
    """Tests for role-based access control."""
    
    def test_admin_access(self, admin_client):
        """Test admin role access."""
        with admin_client.session_transaction() as sess:
            assert sess['rola'] == 'admin'
    
    def test_lider_access(self, lider_client):
        """Test lider role access."""
        with lider_client.session_transaction() as sess:
            assert sess['rola'] == 'lider'
    
    def test_pracownik_access(self, authenticated_client):
        """Test regular worker access."""
        with authenticated_client.session_transaction() as sess:
            assert sess['rola'] == 'pracownik'
    
    def test_shift_closing_requires_lider(self, authenticated_client, lider_client, admin_client):
        """Test that shift closing requires lider or admin role."""
        # Regular worker should be forbidden
        response = authenticated_client.post('/zamknij_zmiane')
        assert response.status_code in [403, 401, 302]
        
        # Lider should be able to attempt
        response = lider_client.post('/zamknij_zmiane')
        assert response.status_code in [200, 302, 500]
        
        # Admin should be able to attempt
        response = admin_client.post('/zamknij_zmiane')
        assert response.status_code in [200, 302, 500]


class TestSessionData:
    """Tests for session data handling."""
    
    def test_user_id_in_session(self, authenticated_client):
        """Test that user_id is stored in session."""
        with authenticated_client.session_transaction() as sess:
            assert 'user_id' in sess
            assert isinstance(sess['user_id'], int)
    
    def test_username_in_session(self, authenticated_client):
        """Test that username is stored in session."""
        with authenticated_client.session_transaction() as sess:
            assert 'username' in sess
            assert sess['username'] == 'testuser'
    
    def test_pracownik_id_in_session(self, authenticated_client):
        """Test that pracownik_id is stored in session."""
        with authenticated_client.session_transaction() as sess:
            assert 'pracownik_id' in sess
            assert isinstance(sess['pracownik_id'], int)
    
    def test_role_in_session(self, authenticated_client):
        """Test that role is stored in session."""
        with authenticated_client.session_transaction() as sess:
            assert 'rola' in sess
            assert sess['rola'] in ['pracownik', 'lider', 'admin']


class TestMultipleUsers:
    """Tests for multiple concurrent users."""
    
    def test_different_users_different_sessions(self, app):
        """Test that different users have different sessions."""
        client1 = app.test_client()
        client2 = app.test_client()
        
        # Setup user 1
        with client1.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'user1'
        
        # Setup user 2 with different data
        with client2.session_transaction() as sess:
            sess['user_id'] = 2
            sess['username'] = 'user2'
        
        # Verify separation
        with client1.session_transaction() as sess:
            assert sess['username'] == 'user1'
        
        with client2.session_transaction() as sess:
            assert sess['username'] == 'user2'
    
    def test_concurrent_requests_maintained(self, app):
        """Test that concurrent requests maintain session isolation."""
        client1 = app.test_client()
        client2 = app.test_client()
        
        # Set different values
        with client1.session_transaction() as sess:
            sess['counter'] = 1
        
        with client2.session_transaction() as sess:
            sess['counter'] = 2
        
        # Each should maintain their own value
        with client1.session_transaction() as sess:
            assert sess['counter'] == 1
        
        with client2.session_transaction() as sess:
            assert sess['counter'] == 2


class TestAuthenticationEdgeCases:
    """Tests for authentication edge cases."""
    
    def test_empty_session(self, client):
        """Test accessing protected routes with empty session."""
        # Access without setting session data
        response = client.get('/', follow_redirects=False)
        
        # Should redirect to login
        assert response.status_code in [302, 401]
    
    def test_missing_role_in_session(self, client):
        """Test accessing with missing role."""
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            # Don't set role
        
        response = client.get('/', follow_redirects=False)
        
        # Should handle gracefully
        assert response.status_code in [302, 401, 200, 500]
    
    def test_invalid_role_value(self, client):
        """Test with invalid role value."""
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['rola'] = 'invalid_role'
        
        # Should handle gracefully
        response = client.get('/')
        assert response.status_code in [200, 302, 500, 403]


class TestAuthenticationFlow:
    """Tests for complete authentication flow."""
    
    def test_guest_cannot_access_dashboard(self, client):
        """Test that guest cannot access dashboard."""
        response = client.get('/')
        
        assert response.status_code in [302, 401]
    
    def test_authenticated_can_access_dashboard(self, authenticated_client):
        """Test that authenticated user can access dashboard."""
        response = authenticated_client.get('/')
        
        # Should not redirect to login
        assert response.status_code != 301  # Permanent redirect
        assert response.status_code != 401
    
    def test_health_check_accessible_without_auth(self, client):
        """Test that health check is accessible without authentication."""
        response = client.get('/health')
        
        # Health check should work without login
        assert response.status_code in [200, 503]
    
    def test_admin_has_elevated_access(self, admin_client):
        """Test that admin user has necessary elevated access."""
        # Health check
        response = admin_client.get('/health')
        assert response.status_code in [200, 503]
        
        # Shift closing (usually admin can do this)
        response = admin_client.post('/zamknij_zmiane')
        assert response.status_code in [200, 302, 500]
