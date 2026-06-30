import mysql.connector

c = mysql.connector.connect(host='filipinka.myqnapcloud.com', port=3307, user='biblioteka', password='Filipinka2025', database='biblioteka')
cur = c.cursor(dictionary=True)

cur.execute('''
    SELECT p.*, plan.data_planu, plan.produkt 
    FROM palety_agro p 
    LEFT JOIN plan_agro plan ON p.plan_id = plan.id 
    LEFT JOIN magazyn_palety_agro m ON p.id = m.paleta_workowanie_id 
    WHERE p.status IN ('do_przyjecia', 'przyjeta') AND m.id IS NULL
''')
pallets = cur.fetchall()

print(f"Found {len(pallets)} missing pallets.")

count = 0
for p in pallets:
    # Insert into magazyn_palety_agro
    cur.execute('''
        INSERT INTO magazyn_palety_agro 
        (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, lokalizacja, user_login, nr_palety, nr_plomby, data_potwierdzenia, data_produkcji, linia, typ_opakowania) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, DATE(%s), 'AGRO', 'bags')
    ''', (
        p['id'], 
        p['plan_id'], 
        p['data_planu'], 
        p['produkt'] or 'Wyrób Gotowy AGRO', 
        float(p['waga'] or 0), 
        float(p['waga_brutto'] or 0), 
        float(p['tara'] or 0), 
        'MGW01', 
        p['dodal_login'] or 'system', 
        p['nr_palety'], 
        p['nr_plomby'], 
        p['data_dodania'], 
        p['data_dodania']
    ))
    
    # Update palety_agro
    cur.execute('UPDATE palety_agro SET status="w_magazynie" WHERE id=%s', (p['id'],))
    count += 1

c.commit()
print(f"Inserted and updated {count} pallets.")
