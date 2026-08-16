import codecs

with codecs.open('a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/palety_routes.py', 'r', encoding='utf-8') as f:
    source = f.read()

# I will replace dodaj_palete body.
import re

new_dodaj_palete = """    def dodaj_palete(plan_id):
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
            plan_id=plan_id,
            linia=linia,
            waga_palety=waga_palety,
            nr_plomby=nr_plomby,
            data_produkcji=data_produkcji,
            printer_ip=printer_ip,
            printer_name=printer_name,
            user_login=user_login,
            app_obj=app_obj,
            is_ajax=is_ajax,
            safe_return_url=safe_return()
        )
        
        if is_ajax:
            if status_code >= 400:
                return jsonify({'success': False, 'message': result}), status_code
            return jsonify({'success': True, 'message': result}), status_code
            
        if status_code >= 400:
            return (result, status_code)
        
        flash(result, 'success')
        return redirect(redirect_url or safe_return())"""

# And similarly for potwierdz_palete, usun_palete, edytuj_palete, etc.
