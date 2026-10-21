"""Authorize shared raw stock by physical warehouse, never by its legacy line field."""
from app.core.production_permissions import _page_allowed
from app.utils.location_validator import get_warehouse_zone


def is_shared_raw_resource(resource):
    kind = str(resource.get('inventory_type') or resource.get('typ') or '').strip().casefold()
    return kind.startswith('surowiec') or str(resource.get('inventory_key') or '').upper() == 'SUR'


def shared_raw_stock_allowed(resource, context_line, *, write=False):
    """Warehouse pages retain their ACL names; raw pallets have no production owner."""
    context_line = str(context_line or '').strip().upper()
    if context_line not in {'PSD', 'AGRO', 'OSIP', 'ALL'}:
        return False
    location = str(resource.get('lokalizacja') or '').strip().upper()
    zone = get_warehouse_zone(location)
    warehouse_page = {'MP01': 'AGRO', 'MS01': 'PSD', 'OSIP': 'OSIP'}.get(zone)
    if location.replace('_', '').replace('-', '').startswith('MDO01'):
        warehouse_page = 'AGRO'
    if warehouse_page:
        return _page_allowed(warehouse_page, 'magazyn', write=write)
    # ALL is a document/UI scope, not a production owner of raw stock.
    # Unknown physical locations still require permission for the whole scope.
    halls = ('PSD', 'AGRO', 'OSIP') if context_line == 'ALL' else (context_line,)
    return all(_page_allowed(hall, 'magazyn', write=write) for hall in halls)
