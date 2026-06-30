"""Magazyny nowe management module."""
from .blueprint import magazyny_nowe_bp

from . import views
from . import api_pallets
from . import api_production

__all__ = ['magazyny_nowe_bp']
