"""Warehouse materials are shared; production halls do not own stock."""
from flask import session

SHARED_MATERIAL_TYPES = {'Surowiec', 'Opakowanie', 'Dodatek'}
SHARED_MATERIAL_TABLES = {'magazyn_surowce', 'magazyn_opakowania', 'magazyn_dodatki'}


def is_shared_material(resource):
    kind = str(resource.get('inventory_type') or resource.get('typ') or '').strip().casefold()
    return kind.startswith(('surowiec', 'opakowanie', 'dodatek')) or str(resource.get('inventory_key') or '').upper() in {'SUR', 'OPK', 'DOD'}


def shared_material_access():
    return bool(session.get('zalogowany'))
