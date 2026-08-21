"""Magazyny nowe management module."""
from .blueprint import warehouse_v2_bp

from . import views
from . import api_pallets
from . import api_production
from . import api_orders
from . import zaladunki_routes
from . import production_consumption_routes

__all__ = ['warehouse_v2_bp']
