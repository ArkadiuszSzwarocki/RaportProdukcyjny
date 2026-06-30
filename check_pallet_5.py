
import sys, os
sys.path.append(os.getcwd())
from app.core.factory import create_app
from app.db import get_db_connection, get_table_name

app = create_app(init_db=False)
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    table_plan = get_table_name('plan_produkcji', 'AGRO')
    table_pal = get_table_name('palety_workowanie', 'AGRO')
    
    cursor.execute(f'SELECT id, produkt, status FROM {table_plan} ORDER BY id DESC LIMIT 1')
    plan = cursor.fetchone()
    if not plan:
        print('No plans')
        sys.exit(0)
        
    print('Plan:', plan['id'], '-', plan['produkt'], '-', plan['status'])
    
    cursor.execute(f'SELECT id, nr_palety, waga, status, data_dodania FROM {table_pal} WHERE plan_id = %s ORDER BY id ASC LIMIT 20', (plan['id'],))
    pallets = cursor.fetchall()
    
    for i, p in enumerate(pallets):
        print('Pallet', i+1, '(ID:', p['id'], ', QA:', p['nr_palety'], '): status=', p['status'], ', dodana=', p['data_dodania'])

