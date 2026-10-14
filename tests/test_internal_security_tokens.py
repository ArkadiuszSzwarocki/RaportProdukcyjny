import time

from app.utils.security_tokens import (
    generate_internal_print_token,
    verify_internal_print_token,
)


def test_internal_print_token_is_bound_to_endpoint(app):
    with app.app_context():
        token = generate_internal_print_token('/agro/raport_palet', expires_in_sec=60)
        assert verify_internal_print_token('/agro/raport_palet', token) is True
        assert verify_internal_print_token('/admin/secret', token) is False


def test_internal_print_token_ttl_is_capped(app):
    with app.app_context():
        token = generate_internal_print_token('/agro/raport_palet', expires_in_sec=999999)
        expires_at = int(token.split(':', 1)[0])
        remaining = expires_at - int(time.time())
        assert 1 <= remaining <= 300
        assert verify_internal_print_token('/agro/raport_palet', token) is True


def test_internal_print_token_rejects_invalid_endpoint(app):
    with app.app_context():
        token = generate_internal_print_token('/agro/raport_palet')
        assert verify_internal_print_token('agro/raport_palet', token) is False
