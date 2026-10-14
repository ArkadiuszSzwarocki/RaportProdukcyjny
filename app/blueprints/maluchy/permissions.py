# cspell:words boczkmar szwarark
"""Shared authorization for emergency bucket assignment."""
from flask import session


def can_emergency_dump_bucket() -> bool:
    """Allow only the named supervisor roles/accounts in an authenticated session."""
    role = str(session.get('rola') or '').strip().casefold().replace(' ', '_').replace('-', '_')
    login = str(session.get('login') or '').strip().casefold()
    return bool(session.get('zalogowany')) and (
        role in {'masteradmin', 'master_admin', 'zarzad', 'zarząd'}
        or login in {'szwarark', 'boczkmar'}
    )
