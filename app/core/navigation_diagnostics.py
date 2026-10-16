# cspell:words szwarark boczkmar
"""Narrow, credential-free evidence for unexpected dashboard navigation."""
import json
import logging
import math
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import Blueprint, g, jsonify, request, session

ACCOUNTS = frozenset({'szwarark', 'boczkmar'})
REASONS = frozenset({'deadline', 'role_activated_elsewhere', 'role_disabled_elsewhere',
                     'eligibility_lost', 'manual_disable', 'dashboard_link', 'unattributed'})
VIEWS = frozenset({'scanner', 'dashboard', 'zasyp', 'workowanie', 'warehouse', 'login', 'other', 'unknown'})


def observed():
    return bool(session.get('zalogowany')) and str(session.get('login') or '').casefold() in ACCOUNTS


def view_of(url):
    try:
        parsed = urlsplit(url)
        if parsed.netloc and parsed.netloc != request.host:
            return 'unknown'
        if '/scanner' in parsed.path:
            return 'scanner'
        if parsed.path == '/':
            from urllib.parse import parse_qs
            section = parse_qs(parsed.query).get('sekcja', ['dashboard'])[0].casefold()
            return section if section in {'dashboard', 'zasyp', 'workowanie'} else 'other'
        if parsed.path.startswith('/warehouse-v2'):
            return 'warehouse'
        if parsed.path.startswith('/login'):
            return 'login'
        return 'other' if parsed.path else 'unknown'
    except ValueError:
        return 'unknown'


def record_role_event(reason):
    if observed():
        _record('role_transition', reason=reason)


def _record(phase, **data):
    value = dict(time_utc=datetime.now(timezone.utc).isoformat(), phase=phase, login=str(session.get('login')).casefold(),
                 role=str(session.get('rola') or ''),
                 account_role=str(session.get('_account_role') or ''),
                 endpoint=request.endpoint, method=request.method, **data)
    logging.getLogger('audit').warning('NAVIGATION_DIAGNOSTIC %s', json.dumps(value, ensure_ascii=True))


def register_navigation_diagnostics(app):
    blueprint = Blueprint('navigation_diagnostics', __name__)
    last_report = {}

    @app.before_request
    def record_dashboard_arrival():
        if not observed() or request.method != 'GET' or request.path != '/' or view_of(request.url) != 'dashboard':
            return
        mode = request.headers.get('Sec-Fetch-Mode', '')
        if mode and mode not in {'navigate', 'nested-navigate'}:
            return
        g.navigation_diagnostic_id = secrets.token_hex(8)
        _record('server_arrival', event_id=g.navigation_diagnostic_id,
                previous_view=view_of(request.referrer or ''),
                user_activation=request.headers.get('Sec-Fetch-User') == '?1',
                fetch_mode=request.headers.get('Sec-Fetch-Mode') in {'navigate', 'nested-navigate'})

    @app.after_request
    def record_server_redirect(response):
        if observed() and response.status_code in (301, 302, 303, 307, 308) and view_of(response.headers.get('Location', '')) == 'dashboard':
            _record('server_redirect', status=response.status_code, previous_view=view_of(request.url))
        return response

    @app.context_processor
    def diagnostic_config():
        if not observed():
            return {'navigation_diagnostics': None}
        if not session.get('_navigation_diagnostic_csrf'):
            session['_navigation_diagnostic_csrf'] = secrets.token_urlsafe(32)
        return {'navigation_diagnostics': dict(csrf=session['_navigation_diagnostic_csrf'],
                event_id=getattr(g, 'navigation_diagnostic_id', ''),
                owner=str(session.get('login')).casefold())}

    @blueprint.post('/auth/navigation-diagnostics')
    def report():
        if not observed():
            return jsonify(success=False), 403
        if not request.content_length or request.content_length > 4096:
            return jsonify(success=False), 413
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(success=False), 400
        token = payload.get('csrf')
        expected = session.get('_navigation_diagnostic_csrf')
        if not isinstance(token, str) or not expected or not secrets.compare_digest(token, expected):
            return jsonify(success=False), 403
        login = str(session['login']).casefold()
        now = time.monotonic()
        if now - last_report.get(login, -10) < 1:
            return jsonify(success=False), 429
        last_report[login] = now
        reason = payload.get('reason')
        source = payload.get('previous_view')
        navigation = payload.get('navigation_type')
        event_id = str(payload.get('event_id') or '')
        def number(name):
            raw = payload.get(name)
            return round(raw, 3) if type(raw) in (int, float) and 0 <= raw <= 86400000 and math.isfinite(raw) else None
        _record('client_arrival', event_id=event_id if len(event_id) == 16 and all(c in '0123456789abcdef' for c in event_id) else '',
                reason=reason if isinstance(reason, str) and reason in REASONS else 'unattributed',
                previous_view=source if isinstance(source, str) and source in VIEWS else 'unknown',
                navigation_type=navigation if navigation in ('navigate', 'reload', 'back_forward') else 'unknown',
                page_age_ms=number('page_age_ms'), departure_age_ms=number('departure_age_ms'),
                previous_active=payload.get('previous_active') if type(payload.get('previous_active')) is bool else None,
                observed_active=payload.get('observed_active') if type(payload.get('observed_active')) is bool else None,
                observed_eligible=payload.get('observed_eligible') if type(payload.get('observed_eligible')) is bool else None)
        return jsonify(success=True)

    app.register_blueprint(blueprint)
