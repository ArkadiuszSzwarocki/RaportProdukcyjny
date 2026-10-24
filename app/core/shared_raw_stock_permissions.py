"""Raw stock belongs to the shared warehouse, not to a production hall."""
from app.core.shared_inventory_permissions import shared_material_access


def is_shared_raw_resource(resource):
    kind = str(resource.get('inventory_type') or resource.get('typ') or '').strip().casefold()
    return kind.startswith('surowiec') or str(resource.get('inventory_key') or '').upper() == 'SUR'


def shared_raw_stock_allowed(resource, context_line, *, write=False):
    return shared_material_access()
