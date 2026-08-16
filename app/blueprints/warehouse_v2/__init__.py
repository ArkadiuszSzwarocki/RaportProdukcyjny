"""Magazyny nowe management module."""
from .blueprint import warehouse_v2_bp

from . import views
from . import api_pallets
from . import api_production
from . import api_orders

__all__ = ['warehouse_v2_bp']
