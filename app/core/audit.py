"""Audit logging helpers.

Writes human-readable user-action records to logs/audit.log via the
``audit`` logger.  Every entry has the format:

    2026-03-20 18:45:09 AUDIT: jan.kowalski [magazynier] — ACTION — DETAIL
"""

import logging


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
    if detail:
        logger.info('%s [%s] — %s — %s', user, role, action, detail)
    else:
        logger.info('%s [%s] — %s', user, role, action)
