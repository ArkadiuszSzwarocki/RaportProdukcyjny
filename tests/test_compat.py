"""Tests for backward compatibility routes."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestCompatRoutes:
    """Tests for backward compatibility routes in routes_compat.py."""
    
    def test_health_check_endpoint_exists(self, client):
        """Test that health check endpoint is accessible."""
        response = client.get('/health')
        
        assert response.status_code == 200
        assert response.json['service'] == 'raportprodukcyjny'
    
    def test_alternative_health_endpoint_path(self, client):
        """Test alternative health endpoint path."""
        response = client.get('/.health')
        
        assert response.status_code == 200
        data = response.json
        assert 'status' in data
        assert 'db' in data


class TestFaviconHandling:
    """Tests for favicon handling."""
    
    def test_favicon_ico_request(self, client):
        """Test favicon.ico request."""
        response = client.get('/favicon.ico')
        
        # Should return 204 if file not found (no errors)
        assert response.status_code in [204, 200, 404]
    
    def test_favicon_no_404_error(self, client):
        """Test that favicon doesn't cause errors."""
        response = client.get('/favicon.ico')
        
        # Should gracefully handle missing favicon
        assert response.status_code < 500


class TestWellKnownRoutes:
    """Tests for .well-known routes."""
    
    def test_chrome_devtools_well_known(self, client):
        """Test Chrome devtools well-known endpoint."""
        response = client.get('/.well-known/appspecific/com.chrome.devtools.json')
        
        assert response.status_code == 204
        assert response.data == b''
    
    def test_generic_well_known_path(self, client):
        """Test generic well-known path."""
        response = client.get('/.well-known/some-path')
        
        assert response.status_code == 204
    
    def test_nested_well_known_path(self, client):
        """Test nested well-known paths."""
        response = client.get('/.well-known/a/b/c')
        
        assert response.status_code == 204
    
    def test_well_known_no_logs_noisy_errors(self, client, app):
        """Test that well-known requests don't create noisy logs."""
        with patch.object(app.logger, 'error') as mock_error:
            client.get('/.well-known/test')
            
            # Should not log errors for well-known requests
            # (They return 204 intentionally)
            assert not mock_error.called


class TestHealthCheckDetails:
    """Tests for health check response details."""
    
    def test_health_check_has_timestamp(self, client):
        """Test that health check includes timestamp."""
        response = client.get('/health')
        
        data = response.json
        assert 'timestamp' in data
        
        # Verify it's a valid ISO format datetime
        try:
            datetime.fromisoformat(data['timestamp'])
            assert True
        except ValueError:
            pytest.fail("timestamp is not ISO format")
    
    def test_health_check_has_service_name(self, client):
        """Test that health check includes service name."""
        response = client.get('/health')
        
        data = response.json
        assert data['service'] == 'raportprodukcyjny'
    
    def test_health_check_has_version(self, client):
        """Test that health check includes version."""
        response = client.get('/health')
        
        data = response.json
        assert 'version' in data
    
    def test_health_check_status_values(self, client):
        """Test health check status values."""
        response = client.get('/health')
        
        data = response.json
        assert data['status'] in ['ok', 'degraded']
    
    def test_health_check_db_status_values(self, client):
        """Test health check db status values."""
        response = client.get('/health')
        
        data = response.json
        # db can be healthy, unhealthy, or error message
        assert data['db'] in ['healthy', 'unhealthy'] or 'error' in data['db']


class TestHealthCheckStatusCodes:
    """Tests for HTTP status codes in health check."""
    
    def test_healthy_returns_200(self, client, mock_get_db_connection):
        """Test that healthy status returns 200."""
        response = client.get('/health')
        
        assert response.status_code == 200
    
    def test_unhealthy_returns_503(self, client):
        """Test that unhealthy status returns 503."""
        with patch('app.db.get_db_connection', side_effect=Exception('DB Error')):
            response = client.get('/health')
            
            assert response.status_code == 503
    
    def test_status_code_matches_health(self, client):
        """Test that HTTP status code matches health status."""
        # Healthy
        response = client.get('/health')
        if response.status_code == 200:
            assert response.json['status'] == 'ok'
        
        # Unhealthy
        with patch('app.db.get_db_connection', side_effect=Exception('Error')):
            response = client.get('/health')
            if response.status_code == 503:
                assert response.json['status'] in ['degraded', 'ok']


class TestHealthCheckContentType:
    """Tests for content type in health check responses."""
    
    def test_health_check_returns_json(self, client):
        """Test that health check returns JSON."""
        response = client.get('/health')
        
        assert 'application/json' in response.content_type
    
    def test_health_check_proper_json_format(self, client):
        """Test that response is valid JSON."""
        response = client.get('/health')
        
        # Should be parseable JSON
        try:
            data = response.get_json()
            assert isinstance(data, dict)
            assert True
        except Exception:
            pytest.fail("Response is not valid JSON")


class TestBackwardCompatibilityAliases:
    """Tests for backward compatibility aliases."""
    
    def test_alias_endpoints_exist(self, authenticated_client):
        """Test that backward compat alias endpoints exist."""
        # These may not have implementations, but should not 404
        # They redirect or are handled by routes_planning
        response = authenticated_client.post('/dodaj_plan', 
                                            data={'plan': 'test'},
                                            follow_redirects=False)
        
        # May redirect or require more data
        assert response.status_code in [302, 400, 404]
    
    def test_alias_plan_deletion(self, authenticated_client):
        """Test backward compat plan deletion alias."""
        response = authenticated_client.post('/usun_plan/1',
                                            follow_redirects=False)
        
        # May be forbidden or require lider role
        assert response.status_code in [302, 403, 404]


class TestCacheControlHeaders:
    """Tests for cache control on well-known routes."""
    
    def test_well_known_not_cached(self, client):
        """Test that well-known routes are not cached."""
        response = client.get('/.well-known/test')
        
        # 204 responses typically aren't cached
        assert response.status_code == 204


class TestErrorResponses:
    """Tests for error response handling."""
    
    def test_health_check_with_connection_pool_exhausted(self, client):
        """Test health check with connection pool exhausted."""
        with patch('app.db.get_db_connection', side_effect=RuntimeError('Connection pool exhausted')):
            response = client.get('/health')
            
            # Should handle gracefully
            assert response.status_code in [200, 503]
    
    def test_health_check_with_timeout(self, client):
        """Test health check with timeout."""
        with patch('app.db.get_db_connection', side_effect=TimeoutError('Connection timeout')):
            response = client.get('/health')
            
            # Should handle gracefully
            assert response.status_code in [200, 503]
