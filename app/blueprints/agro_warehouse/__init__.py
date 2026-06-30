"""Agro warehouse management module."""
from .blueprint import agro_warehouse_bp

from . import tank_assignment
from . import views
from . import api_inventory
from . import api_packaging
from . import api_deliveries
from . import api_reports
from . import api_core

__all__ = ['agro_warehouse_bp']
