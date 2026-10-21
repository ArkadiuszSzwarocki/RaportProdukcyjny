"""Static errors must not survive a later application release in browser caches."""
import pytest
from flask import Flask
from app.core.middleware import add_cache_headers


@pytest.mark.parametrize("status", [200, 206, 304])
def test_successful_static_response_keeps_public_cache(status):
    app = Flask(__name__)
    with app.test_request_context("/static/example.js"):
        response = add_cache_headers(app)(app.response_class(status=status))
    assert response.headers["Cache-Control"] == "public, max-age=86400"


@pytest.mark.parametrize("status", [403, 404, 500])
def test_static_error_cannot_be_cached(status):
    app = Flask(__name__)
    with app.test_request_context("/static/example.js"):
        response = add_cache_headers(app)(app.response_class(status=status))
    assert "no-store" in response.headers["Cache-Control"]


def test_dynamic_response_remains_private():
    app = Flask(__name__)
    with app.test_request_context("/api/example"):
        response = add_cache_headers(app)(app.response_class(status=200))
    assert "no-store" in response.headers["Cache-Control"]
