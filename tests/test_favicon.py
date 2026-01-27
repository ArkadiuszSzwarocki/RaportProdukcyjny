def test_favicon_route():
    from app import app
    client = app.test_client()
    resp = client.get('/favicon.ico')
    # Accept 200 (file served) or 204 (no content when no favicon present)
    assert resp.status_code in (200, 204)
