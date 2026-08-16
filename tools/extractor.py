import ast
import codecs

routes_path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/palety_routes.py'
with codecs.open(routes_path, 'r', encoding='utf-8') as f:
    source = f.read()
lines = source.splitlines()
tree = ast.parse(source)

main_func = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'register_palety_routes':
        main_func = node
        break

for node in main_func.body:
    if isinstance(node, ast.FunctionDef):
        name = node.name
        if name in ['dodaj_palete', 'potwierdz_palete', 'usun_palete', 'edytuj_palete', 'usun_palete_ajax', 'edytuj_palete_ajax']:
            code = '\n'.join(lines[node.lineno-1:node.end_lineno])
            with codecs.open(f'a:/GitHub/RaportProdukcyjny/scratch/{name}.py', 'w', encoding='utf-8') as f:
                f.write(code)
print("Extracted functions")
