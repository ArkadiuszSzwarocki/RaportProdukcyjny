import ast
import os
import codecs

filepath = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/management.py'
with codecs.open(filepath, 'r', encoding='utf-8') as f:
    source = f.read()

lines = source.splitlines()

tree = ast.parse(source)

# Find the main register function
main_func = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'register_warehouse_management_routes':
        main_func = node
        break

def get_source(node):
    return '\n'.join(lines[node.lineno-1:node.end_lineno])

# Grouping
groups = {
    'palety': ['dodaj_palete', 'dodaj_palete_page', 'edytuj_palete_page', 'confirm_delete_palete_page', 'potwierdz_palete_page', 'potwierdz_palete', 'usun_palete', 'edytuj_palete', 'edytuj_palete_ajax', 'usun_palete_ajax', '_resolve_plan_id_for_paleta'],
    'szarze': ['confirm_delete_szarze_page', 'edytuj_szarze_page', 'edytuj_szarze', 'usun_szarze'],
    'printing': ['_select_preferred_printer', '_list_active_printers', '_async_print_label', 'drukuj_etykiete', 'drukuj_etykiete_zpl', '_append_candidate', '_append_bridge_endpoints'],
    'misc': ['_parse_data_produkcji_input', 'update_workowanie_data_produkcji', 'wazenie_magazyn']
}

extracted = {k: [] for k in groups}

for node in main_func.body:
    if isinstance(node, ast.FunctionDef):
        name = node.name
        for group, func_names in groups.items():
            if name in func_names:
                extracted[group].append(get_source(node))
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

for group, codes in extracted.items():
    if not codes: continue
    content = header
    if group == 'palety':
        content += "from .printing_routes import _async_print_label, _select_preferred_printer\n"
        content += "from .misc_routes import _parse_data_produkcji_input\n\n"
        
    func_name = f"register_{group}_routes"
    content += f"def {func_name}(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):\n"
    
    for code in codes:
        # indent code by 4 spaces
        indented = '\n'.join('    ' + line for line in code.splitlines())
        content += indented + '\n\n'
        
    if group == 'printing':
        content += "    return _select_preferred_printer, _async_print_label\n"
    if group == 'misc':
        content += "    return _parse_data_produkcji_input\n"
        
    with codecs.open(f"{routes_dir}/{group}_routes.py", 'w', encoding='utf-8') as f:
        f.write(content)

print("Split completed.")
