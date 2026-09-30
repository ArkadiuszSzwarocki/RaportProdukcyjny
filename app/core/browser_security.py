"""Browser-facing response security headers."""


def register_browser_security_headers(app) -> None:
    """Add low-risk security headers without breaking the legacy inline-script UI."""

    @app.after_request
    def _browser_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
        )
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
        )
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        return response
