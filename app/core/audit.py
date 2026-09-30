"""Audit logging helpers."""

import logging


def _request_audit_meta() -> str:
    """Build compact request metadata for audit entries when in request context."""
    try:
        from flask import request
        from app.core.security_hardening import current_client_ip

        method = (request.method or '').upper()
        path = request.path or ''
        remote_ip = current_client_ip()

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
    """Record a user action to the dedicated audit log."""
    try:
        from flask import session

        user = session.get('login') or 'system'
        role = session.get('rola') or '—'
    except RuntimeError:
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


def security_audit_log(
    event_type: str,
    detail: str = '',
    user_login: str = None,
    client_ip: str = None,
) -> None:
    """Record a structured security event."""
    try:
        from flask import session
        from app.core.security_hardening import current_client_ip

        user = user_login or session.get('login') or 'anonymous'
        role = session.get('rola') or 'none'
        ip = client_ip or current_client_ip()
    except Exception:
        user = user_login or 'system'
        role = 'none'
        ip = client_ip or 'unknown'

    logger = logging.getLogger('audit')
    message = f'[SECURITY] {event_type} | User: {user} ({role}) | IP: {ip}'
    if detail:
        message += f' | {detail}'
    logger.warning(message)
