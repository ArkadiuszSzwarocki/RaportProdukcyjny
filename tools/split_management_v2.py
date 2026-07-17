import ast
import codecs
import os

filepath = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/management.py'
with codecs.open(filepath, 'r', encoding='utf-8') as f:
    source = f.read()

lines = source.splitlines()
tree = ast.parse(source)

main_func = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'register_warehouse_management_routes':
        main_func = node
        break

def get_source(node):
    return '\n'.join(lines[node.lineno-1:node.end_lineno])

# Route Groups
route_groups = {
    'palety': ['dodaj_palete', 'dodaj_palete_page', 'edytuj_palete_page', 'confirm_delete_palete_page', 'potwierdz_palete_page', 'potwierdz_palete', 'usun_palete', 'edytuj_palete', 'edytuj_palete_ajax', 'usun_palete_ajax'],
    'szarze': ['confirm_delete_szarze_page', 'edytuj_szarze_page', 'edytuj_szarze', 'usun_szarze'],
    'printing': ['drukuj_etykiete', 'drukuj_etykiete_zpl'],
    'misc': ['update_workowanie_data_produkcji', 'wazenie_magazyn']
}

# Module level helpers (no closure usage)
helpers = {
    'palety': ['_resolve_plan_id_for_paleta'],
    'szarze': [],
    'printing': ['_select_preferred_printer', '_list_active_printers', '_async_print_label', '_append_candidate', '_append_bridge_endpoints'],
    'misc': ['_parse_data_produkcji_input']
}

# The decorators used by drukuj_etykiete_zpl inside might not be AST top-level, let's just grab by name
# Wait, _append_candidate and _append_bridge_endpoints are inside drukuj_etykiete_zpl!
# If we extract drukuj_etykiete_zpl as a string, it will contain them. That's actually fine, we don't need to extract them separately if they are nested inside it.
helpers['printing'] = ['_select_preferred_printer', '_list_active_printers', '_async_print_label']

extracted_routes = {k: [] for k in route_groups}
extracted_helpers = {k: [] for k in helpers}

# To deal with decorators properly, we can just find them in `main_func.body`
for node in main_func.body:
    if isinstance(node, ast.FunctionDef):
        name = node.name
        # Check if it's a route
        for group, names in route_groups.items():
            if name in names:
                extracted_routes[group].append(get_source(node))
                break
        else:
            # Check if helper
            for group, names in helpers.items():
                if name in names:
                    extracted_helpers[group].append(get_source(node))
                    break

header = """from datetime import date, datetime
import os
import threading

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning.status import PlanningStatusService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id

"""

routes_dir = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes'

for group in route_groups:
    content = header
    
    # Imports between modules if needed
    if group == 'palety':
        content += "from .printing_routes import _async_print_label, _select_preferred_printer\n"
        content += "from .misc_routes import _parse_data_produkcji_input\n"
        content += "from .palety_helpers import _resolve_plan_id_for_paleta\n"
    elif group == 'printing':
        content += "from .palety_helpers import _resolve_plan_id_for_paleta\n"
        
    content += "\n"
    
    # Add helpers at module level
    for h in extracted_helpers.get(group, []):
        # unindent the helper (it was indented by 4 spaces)
        unindented = '\n'.join(line[4:] if line.startswith('    ') else line for line in h.splitlines())
        content += unindented + '\n\n'
        
    func_name = f"register_{group}_routes"
    content += f"def {func_name}(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):\n"
    
    for r in extracted_routes.get(group, []):
        content += '\n'.join('    ' + line[4:] if line.startswith('    ') else '    ' + line for line in r.splitlines()) + '\n\n'
        
    with codecs.open(f"{routes_dir}/{group}_routes.py", 'w', encoding='utf-8') as f:
        f.write(content)

# We need a separate file for palety_helpers because both palety and printing might need it, or we just put it in palety_routes
# Let's put _resolve_plan_id_for_paleta inside palety_helpers.py
content_helper = header + "\n"
for h in extracted_helpers.get('palety', []):
    unindented = '\n'.join(line[4:] if line.startswith('    ') else line for line in h.splitlines())
    content_helper += unindented + '\n\n'
with codecs.open(f"{routes_dir}/palety_helpers.py", 'w', encoding='utf-8') as f:
    f.write(content_helper)

# Generate new management.py
mgmt = header
mgmt += """from .routes.palety_routes import register_palety_routes
from .routes.szarze_routes import register_szarze_routes
from .routes.printing_routes import register_printing_routes
from .routes.misc_routes import register_misc_routes

def register_warehouse_management_routes(
    warehouse_bp,
    *,
    resolve_request_linia,
    resolve_payload_linia,
    update_paleta_workowanie,
    update_paleta_magazyn,
    safe_return,
):
    register_palety_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
    register_szarze_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
    register_printing_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
    register_misc_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
"""
with codecs.open(filepath, 'w', encoding='utf-8') as f:
    f.write(mgmt)
    
print("v2 split completed!")
