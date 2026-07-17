import os
import ast
import codecs

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

extracted = {}
for node in main_func.body:
    if isinstance(node, ast.FunctionDef) and node.name in ['dodaj_palete', 'potwierdz_palete', 'usun_palete', 'edytuj_palete', 'usun_palete_ajax', 'edytuj_palete_ajax']:
        extracted[node.name] = '\n'.join(lines[node.lineno-1:node.end_lineno])

# Let's save the extracted raw functions to inspect them easily
for name, code in extracted.items():
    with codecs.open(f'a:/GitHub/RaportProdukcyjny/scratch/raw_{name}.py', 'w', encoding='utf-8') as f:
        f.write(code)

print("Saved raw functions")
