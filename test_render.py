import sys
sys.path.insert(0, '.')
from app.core.factory import create_app
from app.services.agro_warehouse_service import AgroWarehouseService
from flask import render_template

app = create_app()
app.config['TESTING'] = True

with app.test_request_context('/agro/magazyn'):
    try:
        inventory = AgroWarehouseService.get_inventory_grouped(linia='Agro')
        history = AgroWarehouseService.get_history(limit=50, linia='Agro')
        pending = AgroWarehouseService.get_history(status='OCZEKUJACE', linia='Agro')
        dictionary = AgroWarehouseService.get_dictionary()
        
        html = render_template('agro_warehouse/index.html',
                               inventory=inventory,
                               history=history,
                               pending=pending,
                               dictionary=dictionary,
                               current_plan_id=None,
                               current_plan_name=None,
                               rola='admin')
        with open('test_output.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"SUCCESS! Rendered HTML length: {len(html)}")
    except Exception as e:
        import traceback
        print("ERROR RENDERING:")
        traceback.print_exc()
