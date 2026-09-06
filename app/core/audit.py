"""Audit logging helpers.

Writes human-readable user-action records to logs/audit.log via the
``audit`` logger.  Every entry has the format:

    2026-03-20 18:45:09 AUDIT: jan.kowalski [magazynier] — ACTION — DETAIL
"""

import logging


def _request_audit_meta() -> str:
    """Build compact request metadata for audit entries when in request context."""
    try:
        from flask import request
    except Exception:
        return ''

    try:
        method = (request.method or '').upper()
        path = request.path or ''
        remote_ip = request.headers.get('X-Forwarded-For') or request.remote_addr or ''
        remote_ip = str(remote_ip).split(',')[0].strip() if remote_ip else ''

        # Explicit UI origin sent by forms/buttons. Fallback to generic request type.
        ui_trigger = (
            request.form.get('ui_trigger')
            or request.args.get('ui_trigger')
            or request.form.get('ui_source')
            or request.args.get('ui_source')
            or ''
        )
        if not ui_trigger:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                ui_trigger = 'ajax'
            elif method == 'POST':
                ui_trigger = 'form:post'
            else:
                ui_trigger = 'page'

        parts = []
        if method and path:
            parts.append(f'req={method} {path}')
        if remote_ip:
            parts.append(f'ip={remote_ip}')
        if ui_trigger:
            parts.append(f'ui={ui_trigger}')
        return ', '.join(parts)
    except Exception:
        return ''


def audit_log(action: str, detail: str = '') -> None:
    """Record a user action to the dedicated audit log.

    Args:
        action: Short description of what was done (in Polish), e.g.
                ``'Zalogował się'``, ``'Potwierdził paletę'``.
        detail: Optional extra context, e.g. ``'ID=123, produkt=Mąka, 250 kg'``.
    """
    try:
        from flask import session
        user = session.get('login') or 'system'
        role = session.get('rola') or '—'
    except RuntimeError:
        # Outside request context (e.g. background thread / tests)
        user = 'system'
        role = '—'

    logger = logging.getLogger('audit')
    request_meta = _request_audit_meta()
    if request_meta:
        detail = f'{detail}, {request_meta}' if detail else request_meta

    if detail:
        logger.info('%s [%s] — %s — %s', user, role, action, detail)
    else:
        logger.info('%s [%s] — %s', user, role, action)


def security_audit_log(event_type: str, detail: str = '', user_login: str = None, client_ip: str = None) -> None:
    """Record a structured security event (e.g. CSRF_BLOCKED, RATE_LIMIT_LOCKOUT, PASSWORD_CHANGED).
    
    Args:
        event_type: Uppercase event identifier (e.g. 'FAILED_LOGIN', 'CSRF_BLOCKED')
        detail: Human-readable context
        user_login: Explicit login if session is unauthenticated
        client_ip: Explicit client IP if provided
    """
    try:
        from flask import session, request
        user = user_login or session.get('login') or 'anonymous'
        role = session.get('rola') or 'none'
        ip = client_ip or request.headers.get('X-Forwarded-For') or request.remote_addr or 'unknown'
        ip = str(ip).split(',')[0].strip()
    except Exception:
        user = user_login or 'system'
        role = 'none'
        ip = client_ip or 'unknown'

    logger = logging.getLogger('audit')
    msg = f"[SECURITY] {event_type} | User: {user} ({role}) | IP: {ip}"
    if detail:
        msg += f" | {detail}"
    logger.warning(msg)
