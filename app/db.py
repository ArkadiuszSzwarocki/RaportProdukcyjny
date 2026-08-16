"""
Plik DB.py jako Deprecated Proxy po refaktoryzacji.
"""
import warnings

warnings.warn("app.db is deprecated. Import directly from app.core.database or app.repositories", DeprecationWarning, stacklevel=2)

from app.core.database import *
from app.core.database_setup import *
from app.repositories.production_repository import *
from app.repositories.notification_repository import *
from app.repositories.session_repository import *
from app.repositories.push_repository import *
