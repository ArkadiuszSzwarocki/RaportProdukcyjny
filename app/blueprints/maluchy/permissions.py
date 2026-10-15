# cspell:words boczkmar szwarark
"""Shared authorization for emergency bucket assignment."""
from flask import session


def can_emergency_dump_bucket() -> bool:
    """Require an active supervisor role in an authenticated session."""
    role = str(session.get('rola') or '').strip().casefold().replace(' ', '_').replace('-', '_')
    return bool(session.get('zalogowany')) and (
        role in {'masteradmin', 'master_admin', 'zarzad', 'zarząd'}
    )
