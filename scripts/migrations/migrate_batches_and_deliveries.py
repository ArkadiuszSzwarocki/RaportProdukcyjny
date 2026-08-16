import uuid
import json
from datetime import timedelta
from app.db import get_db_connection

def migrate():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # 1. Fetch pallets missing batch numbers
    cur.execute('''
        SELECT id, nr_palety, produkt, waga_netto, lokalizacja, typ_opakowania, user_login, created_at 
        FROM magazyn_palety 
        WHERE (nr_partii IS NULL OR nr_partii = '')
        ORDER BY produkt, created_at ASC
    ''')
    pallets = cur.fetchall()
    
    if not pallets:
        print('No pallets to migrate.')
        return
        
    print(f'Found {len(pallets)} pallets to migrate.')
    
    # Group by product
    products = {}
    for p in pallets:
        prod = p['produkt']
        if prod not in products:
            products[prod] = []
        products[prod].append(p)
        
    deliveries_to_insert = []
    pallets_to_update = []
    
    batch_counter = 1
    
    for prod, prod_pallets in products.items():
        # Split into chunks of 20
        chunk_size = 20
        for i in range(0, len(prod_pallets), chunk_size):
            chunk = prod_pallets[i:i+chunk_size]
            
            # Use the first pallet's created_at for dates
            first_created_at = chunk[0]['created_at']
            if not first_created_at:
                continue
                
            data_produkcji = first_created_at.date()
            data_przydatnosci = data_produkcji + timedelta(days=180)
            date_str = data_produkcji.strftime('%Y%m%d')
            nr_partii = f'LOT-{date_str}-{batch_counter:04d}'
            batch_counter += 1
            
            user_login = chunk[0]['user_login'] or 'System'
            
            delivery_id = f'MIG-{uuid.uuid4().hex[:8].upper()}'
            
            delivery_items = []
            
            for p in chunk:
                pallets_to_update.append({
                    'id': p['id'],
                    'nr_partii': nr_partii,
                    'data_produkcji': data_produkcji,
                    'data_przydatnosci': data_przydatnosci
                })
                
                delivery_items.append({
                    'id': f'MIG_ITEM_{p["id"]}',
                    'productName': p['produkt'],
                    'netWeight': p['waga_netto'],
                    'nr_partii': nr_partii,
                    'data_produkcji': data_produkcji.strftime('%Y-%m-%d'),
                    'data_przydatnosci': data_przydatnosci.strftime('%Y-%m-%d'),
                    'packageForm': p['typ_opakowania'] or 'bags',
                    'accepted': True,
                    'accepted_by': p['user_login'] or 'System',
                    'accepted_at': p['created_at'].strftime('%Y-%m-%d %H:%M:%S') if p['created_at'] else '',
                    'lokalizacja_przyjecia': p['lokalizacja'],
                    'nr_palety': p['nr_palety']
                })
                
            deliveries_to_insert.append({
                'id': delivery_id,
                'supplier': 'Migracja Historyczna',
                'delivery_date': data_produkcji,
                'status': 'COMPLETED',
                'items': json.dumps(delivery_items),
                'created_by': user_login,
                'created_at': first_created_at,
                'potwierdzone_przez': user_login,
                'potwierdzone_at': first_created_at
            })
            
    # Apply changes
    print(f'Updating {len(pallets_to_update)} pallets with batches and dates...')
    for p in pallets_to_update:
        cur.execute('''
            UPDATE magazyn_palety 
            SET nr_partii = %s, data_produkcji = %s, data_przydatnosci = %s 
            WHERE id = %s
        ''', (p['nr_partii'], p['data_produkcji'], p['data_przydatnosci'], p['id']))
        
    print(f'Inserting {len(deliveries_to_insert)} delivery records...')
    for d in deliveries_to_insert:
        cur.execute('''
            INSERT INTO magazyn_dostawy 
            (id, supplier, delivery_date, status, items, created_by, created_at, potwierdzone_przez, potwierdzone_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (d['id'], d['supplier'], d['delivery_date'], d['status'], d['items'], d['created_by'], d['created_at'], d['potwierdzone_przez'], d['potwierdzone_at']))
        
    conn.commit()
    cur.close()
    conn.close()
    print('Migration completed successfully!')

if __name__ == '__main__':
    migrate()
