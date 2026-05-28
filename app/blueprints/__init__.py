"""Pakiet blueprintów aplikacji.

Ten moduł utrzymuje aliasy kompatybilności dla starszych ścieżek importu
(`app.blueprints.routes_*`), wykorzystywanych m.in. w testach.
"""

from importlib import import_module

# Legacy compatibility aliases for pre-refactor module paths.
routes_auth = import_module('.auth.base', __name__)
routes_production = import_module('.production', __name__)
routes_planning_creation = import_module('.planning.creation', __name__)
routes_scanner = import_module('.scanner.base', __name__)
routes_production_orders = import_module('.production.orders', __name__)
routes_warehouse_management = import_module('.warehouse.management', __name__)

__all__ = [
    'routes_auth',
    'routes_production',
    'routes_planning_creation',
    'routes_scanner',
    'routes_production_orders',
    'routes_warehouse_management',
]
