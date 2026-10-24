"""Warehouse materials are shared; production halls do not own stock."""
from flask import session

SHARED_MATERIAL_TYPES = {'Surowiec', 'Opakowanie', 'Dodatek'}
SHARED_MATERIAL_TABLES = {'magazyn_surowce', 'magazyn_opakowania', 'magazyn_dodatki'}


def is_shared_material(resource):
    kind = str(resource.get('inventory_type') or resource.get('typ') or '').strip().casefold()
    return kind.startswith(('surowiec', 'opakowanie', 'dodatek')) or str(resource.get('inventory_key') or '').upper() in {'SUR', 'OPK', 'DOD'}


def shared_material_access():
    return bool(session.get('zalogowany'))


WAREHOUSE_PAGES = {
    'magazyn', 'psd.magazyn', 'agro.magazyn', 'osip.magazyn',
    'magazyn.view', 'magazyn.pending', 'magazyn.reception', 'magazyn.return',
    'magazyn.agro_total', 'magazyn.agro_packaging',
}
WAREHOUSE_MANAGER_ROLES = {'admin', 'masteradmin', 'zarzad', 'lider'}


def warehouse_role(value=None):
    from app.decorators import _normalize_role
    role = _normalize_role(session.get('rola') if value is None else value)
    return {'operator': 'pracownik', 'stepnpio': 'pracownik',
            'administrator': 'admin', 'zarząd': 'zarzad'}.get(role, role)


def can_manage_orders(role):
    if role is None:
        return False
    return warehouse_role(role) in WAREHOUSE_MANAGER_ROLES | {
        'pracownik', 'magazynier', 'magazyn', 'planista', 'kierownik',
        'brygadzista', 'liderzmiany',
    }


def is_consumption_location(location):
    from app.utils.location_validator import is_production_tank_code
    location = str(location or '').strip().upper()
    return location in {'LP01', 'MASZYNA'} or is_production_tank_code(location)


def can_archive_stock(resource):
    if not shared_material_access():
        return False
    return warehouse_role() in WAREHOUSE_MANAGER_ROLES or is_consumption_location(resource.get('lokalizacja'))
