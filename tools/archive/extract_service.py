import ast
import codecs
import re

routes_path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/palety_routes.py'
service_path = 'a:/GitHub/RaportProdukcyjny/app/services/warehouse_pallet_service.py'

with codecs.open(routes_path, 'r', encoding='utf-8') as f:
    source = f.read()

lines = source.splitlines()
tree = ast.parse(source)

main_func = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'register_palety_routes':
        main_func = node
        break

def get_source(node):
    return '\n'.join(lines[node.lineno-1:node.end_lineno])

# We extract the entire functions, rename them to be staticmethods in WarehousePalletService
extracted_bodies = {}
for node in main_func.body:
    if isinstance(node, ast.FunctionDef) and node.name in ['dodaj_palete', 'potwierdz_palete', 'edytuj_palete', 'usun_palete', 'edytuj_palete_ajax', 'usun_palete_ajax']:
        extracted_bodies[node.name] = get_source(node)

# Service content
service_content = """from datetime import date, datetime
import os
import threading

from flask import current_app

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.services.planning.status import PlanningStatusService
from app.utils.pallet_id import generate_pallet_id

from app.blueprints.warehouse.routes.printing_routes import _select_preferred_printer
from app.blueprints.warehouse.routes.palety_helpers import _resolve_plan_id_for_paleta

class WarehousePalletService:
"""

# Let's clean up the function signatures to pass what they need: request args, forms, session
# Since we just want to move the body without changing it much (to avoid breaking anything),
# we can pass `request`, `session`, `resolve_request_linia`, `update_paleta_workowanie`, `update_paleta_magazyn`, `safe_return`
# Wait, `request` and `session` can be imported directly in the service!
# But Clean Architecture says "Service should not depend on framework". 
# But doing a full rewrite of 4 massive endpoints taking 1000 lines without breaking them is risky.
# Let's extract the form variables in the controller and pass them.

