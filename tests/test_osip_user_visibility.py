"""Tests for OSIP user (GontaArt) authentication, redirection and menu visibility."""

import pytest
from werkzeug.security import check_password_hash
from app.blueprints.auth.base import get_user_redirect_target


def test_gontaart_redirect_target():
    """Test that OSIP group users are redirected to /osip/transfers."""
    target = get_user_redirect_target('magazynier', 'OSIP')
    assert target == '/osip/transfers'


def test_gontaart_login_and_session(client, app):
    """Test logging in as GontaArt user and session variables."""
    response = client.post('/login', data={
        'login': 'GontaArt',
        'haslo': 'Artur2026'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert response.location.endswith('/osip/transfers')

    with client.session_transaction() as sess:
        assert sess.get('zalogowany') is True
        assert sess.get('login') == 'GontaArt'
        assert sess.get('rola') == 'magazynier'
        assert sess.get('grupa') == 'OSIP'


def test_gontaart_index_redirect(client):
    """Test that accessing '/' as GontaArt redirects to /osip/transfers."""
    # Login first
    client.post('/login', data={'login': 'GontaArt', 'haslo': 'Artur2026'})
    
    # Access root page
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302
    assert '/osip/transfers' in response.location


def test_gontaart_sidebar_renders_only_osip(client):
    """Test that OSIP user sidebar renders ONLY Magazyn OSIP."""
    client.post('/login', data={'login': 'GontaArt', 'haslo': 'Artur2026'})
    
    response = client.get('/osip/transfers')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Magazyn OSIP section must be present
    assert 'MAGAZYN OSIP' in html

    # Non-OSIP sections must NOT be present in navigation
    assert 'PRODUKCJA PSD' not in html
    assert 'PRODUKCJA AGRO' not in html
