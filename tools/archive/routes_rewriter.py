import ast
import codecs

with codecs.open('a:/GitHub/RaportProdukcyjny/scratch/palety_routes_old.py', 'r', encoding='utf-8') as f:
    source = f.read()

lines = source.splitlines()
tree = ast.parse(source)

main_func = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'register_palety_routes':
        main_func = node
        break

# Find functions to replace
replacements = {}
for node in main_func.body:
    if isinstance(node, ast.FunctionDef) and node.name in ['dodaj_palete', 'potwierdz_palete', 'usun_palete', 'edytuj_palete', 'usun_palete_ajax', 'edytuj_palete_ajax']:
        replacements[node.name] = (node.lineno - 1, node.end_lineno)

# Sort by start line descending so we can replace from bottom to top without messing up line numbers
sorted_replacements = sorted(replacements.items(), key=lambda x: x[1][0], reverse=True)

dodaj_palete_new = """    def dodaj_palete(plan_id):
        \"\"\"Add paleta (package) to Workowanie buffer.\"\"\"
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        waga_palety = request.form.get('waga_palety', '0')
        nr_plomby = request.form.get('nr_plomby')
        data_produkcji = request.form.get('data_produkcji')
        printer_ip = request.form.get('printer_ip')
        printer_name = request.form.get('printer_name')
        user_login = session.get('login', 'System')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        app_obj = current_app._get_current_object()
        
        result, status_code, redirect_url = WarehousePalletService.dodaj_palete(
            plan_id, linia, waga_palety, nr_plomby, data_produkcji,
            printer_ip, printer_name, user_login, app_obj, is_ajax, safe_return()
        )
        
        if is_ajax:
            return jsonify({'success': status_code < 400, 'message': result}), status_code
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())"""

potwierdz_palete_new = """    def potwierdz_palete(paleta_id):
        \"\"\"Confirm paleta and move it to Magazyn.\"\"\"
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        user_login = session.get('login', 'System')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        app_obj = current_app._get_current_object()
        
        result, status_code, redirect_url = WarehousePalletService.potwierdz_palete(
            paleta_id, linia, user_login, app_obj,
            update_paleta_workowanie, update_paleta_magazyn, is_ajax, safe_return()
        )
        
        if is_ajax:
            return jsonify({'success': status_code < 400, 'message': result}), status_code
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())"""

usun_palete_new = """    def usun_palete(paleta_id):
        \"\"\"Delete unconfirmed paleta.\"\"\"
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        user_login = session.get('login', 'System')
        is_ajax = False
        
        result, status_code, redirect_url = WarehousePalletService.usun_palete(
            paleta_id, linia, user_login, is_ajax, safe_return()
        )
        
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())"""

usun_palete_ajax_new = """    def usun_palete_ajax(paleta_id):
        \"\"\"Delete paleta (AJAX).\"\"\"
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        user_login = session.get('login', 'System')
        is_ajax = True
        
        result, status_code, redirect_url = WarehousePalletService.usun_palete(
            paleta_id, linia, user_login, is_ajax, safe_return()
        )
        
        return jsonify({'success': status_code < 400, 'message': result}), status_code"""

edytuj_palete_new = """    def edytuj_palete(paleta_id):
        \"\"\"Edit paleta weight.\"\"\"
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        waga_palety = request.form.get('waga_palety', '0')
        user_login = session.get('login', 'System')
        is_ajax = False
        
        result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
            paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return()
        )
        
        if status_code != 302:
            flash(result, 'error' if status_code >= 400 else 'success')
        return redirect(redirect_url or safe_return())"""

edytuj_palete_ajax_new = """    def edytuj_palete_ajax(paleta_id):
        \"\"\"Edit paleta weight (AJAX).\"\"\"
        from app.services.warehouse_pallet_service import WarehousePalletService
        linia = resolve_request_linia()
        try:
            req_data = request.get_json() or {}
        except Exception:
            req_data = {}
        waga_palety = req_data.get('waga_palety', '0')
        user_login = session.get('login', 'System')
        is_ajax = True
        
        result, status_code, redirect_url = WarehousePalletService.edytuj_palete(
            paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return()
        )
        
        return jsonify({'success': status_code < 400, 'message': result}), status_code"""

new_blocks = {
    'dodaj_palete': dodaj_palete_new,
    'potwierdz_palete': potwierdz_palete_new,
    'usun_palete': usun_palete_new,
    'usun_palete_ajax': usun_palete_ajax_new,
    'edytuj_palete': edytuj_palete_new,
    'edytuj_palete_ajax': edytuj_palete_ajax_new
}

new_lines = lines[:]
for name, (start, end) in sorted_replacements:
    del new_lines[start:end]
    new_lines.insert(start, new_blocks[name])

# Also we need to add jsonify to imports if not there.
import_str = "from flask import jsonify"
if import_str not in source:
    new_lines.insert(0, import_str)

with codecs.open('a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/palety_routes.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print("Overwritten palety_routes.py")
