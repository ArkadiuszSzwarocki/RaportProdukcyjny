import ast

with open('a:/GitHub/RaportProdukcyjny/app/blueprints/magazyny_nowe/base.py', 'r', encoding='utf-8') as f:
    source = f.read()

tree = ast.parse(source)

funcs = {}

for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        # We need the source of the function, including decorators
        start_lineno = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        end_lineno = node.end_lineno
        lines = source.split('\n')[start_lineno-1:end_lineno]
        funcs[node.name] = '\n'.join(lines)

views_funcs = ['index', 'summary', 'production_status']
api_production_funcs = ['get_production_stations', 'get_station_history']
api_pallets_funcs = ['get_history', 'move_pallet', 'archive_pallet', 'dispatch_pallet', 'rename_pallet', 'update_weight', 'toggle_block', 'pallet_return_to_raw', 'print_pallet_label', 'delete_pallet']

def write_funcs(filename, imports, func_names):
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(imports + '\n\n')
        for name in func_names:
            if name in funcs:
                f.write(funcs[name] + '\n\n')
            else:
                print(f"Function {name} not found!")

# Write views.py
views_imports = """from flask import Blueprint, jsonify, render_template, request, session
from app.db import get_db_connection, get_table_name
from .blueprint import magazyny_nowe_bp"""
write_funcs('a:/GitHub/RaportProdukcyjny/app/blueprints/magazyny_nowe/views.py', views_imports, views_funcs)

# Write api_production.py
api_production_imports = """from flask import Blueprint, jsonify, request, session
from app.db import get_db_connection, get_table_name
from .blueprint import magazyny_nowe_bp"""
write_funcs('a:/GitHub/RaportProdukcyjny/app/blueprints/magazyny_nowe/api_production.py', api_production_imports, api_production_funcs)

# Write api_pallets.py
api_pallets_imports = """from datetime import datetime
import os
from flask import Blueprint, jsonify, request, session
from app.db import get_db_connection, get_table_name
from app.services.magazyny_nowe_service import MagazynyNoweService
from .blueprint import magazyny_nowe_bp"""
write_funcs('a:/GitHub/RaportProdukcyjny/app/blueprints/magazyny_nowe/api_pallets.py', api_pallets_imports, api_pallets_funcs)

print("Split using AST completed.")
