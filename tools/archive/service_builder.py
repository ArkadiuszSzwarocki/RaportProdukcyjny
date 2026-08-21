import os
import codecs
import re

def process_function(filename, func_name):
    with codecs.open(f'a:/GitHub/RaportProdukcyjny/scratch/raw_{filename}.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Remove the route decorator if any
    code = re.sub(r'^\s*@.*?\n', '', code, flags=re.MULTILINE)
    
    # Change signature
    if func_name == 'dodaj_palete':
        code = re.sub(r'def dodaj_palete\(plan_id\):', r'''@staticmethod
    def dodaj_palete(plan_id, linia, waga_palety, nr_plomby, data_produkcji, printer_ip, printer_name, user_login, app_obj, is_ajax, safe_return_url):''', code)
    elif func_name == 'potwierdz_palete':
        code = re.sub(r'def potwierdz_palete\(paleta_id\):', r'''@staticmethod
    def potwierdz_palete(paleta_id, linia, user_login, app_obj, update_paleta_workowanie, update_paleta_magazyn, is_ajax, safe_return_url):''', code)
    elif func_name == 'usun_palete':
        code = re.sub(r'def usun_palete\(paleta_id\):', r'''@staticmethod
    def usun_palete(paleta_id, linia, user_login, is_ajax, safe_return_url):''', code)
    elif func_name == 'edytuj_palete':
        code = re.sub(r'def edytuj_palete\(paleta_id\):', r'''@staticmethod
    def edytuj_palete(paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return_url):''', code)
    
    # Replace request.form.get with variables
    code = code.replace("request.form.get('waga_palety', '0')", "waga_palety")
    code = code.replace("request.form.get('nr_plomby')", "nr_plomby")
    code = code.replace("request.form.get('data_produkcji')", "data_produkcji")
    code = code.replace("request.form.get('printer_ip')", "printer_ip")
    code = code.replace("request.form.get('printer_name')", "printer_name")
    code = code.replace("session.get('login', 'System')", "user_login")
    code = code.replace("session.get('login')", "user_login")
    code = code.replace("request.headers.get('X-Requested-With') == 'XMLHttpRequest'", "is_ajax")
    code = code.replace("current_app._get_current_object()", "app_obj")
    code = code.replace("resolve_request_linia()", "linia")
    code = code.replace("safe_return()", "safe_return_url")
    
    # Fix returns
    # return ('Blad', 400) -> return ('Blad', 400, None)
    code = re.sub(r"return \((.*?),\s*(\d+)\)", r"return (\1, \2, None)", code)
    
    # return jsonify({'success': True, 'message': 'Ok'}) -> return ('Ok', 200, None)
    # Actually, the controller can handle the dict. If we just return (dict, status, None), controller can jsonify it.
    code = re.sub(r"return jsonify\((.*?)\)(,\s*\d+)?", r"return (\1\2, None)", code)
    
    # flash(...)
    code = re.sub(r"flash\((.*?),\s*(.*?)\)", r"# flash(\1, \2)", code)
    
    # return redirect(...)
    code = re.sub(r"return redirect\((.*?)\)", r"return ('OK', 302, \1)", code)
    
    return code

service_code = """from datetime import date, datetime
import os
import threading

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.services.planning.status import PlanningStatusService
from app.utils.pallet_id import generate_pallet_id

from app.blueprints.warehouse.routes.printing_routes import _select_preferred_printer
from app.blueprints.warehouse.routes.palety_helpers import _resolve_plan_id_for_paleta
from app.blueprints.warehouse.routes.printing_routes import _async_print_label

class WarehousePalletService:
"""

for func in ['dodaj_palete', 'potwierdz_palete', 'usun_palete', 'edytuj_palete']:
    service_code += process_function(func, func)
    service_code += "\n\n"

with codecs.open('a:/GitHub/RaportProdukcyjny/app/services/warehouse_pallet_service.py', 'w', encoding='utf-8') as f:
    f.write(service_code)

print("Generated warehouse_pallet_service.py")
