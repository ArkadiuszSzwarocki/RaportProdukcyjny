import mysql.connector

c = mysql.connector.connect(host='filipinka.myqnapcloud.com', port=3307, user='biblioteka', password='Filipinka2025', database='biblioteka')
cur = c.cursor(dictionary=True)

p_id = 348

cur.execute('''
    INSERT INTO magazyn_palety_agro 
    (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, lokalizacja, user_login, nr_palety, nr_plomby, data_potwierdzenia, data_produkcji, linia, typ_opakowania) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, DATE(%s), 'AGRO', 'bags')
''', (
    p_id, 201, '2026-06-19', 'MLECZNA PYCHA BIAŁA', 920.0, 0.0, 25.0, 'MGW01', 'szwarark', 'AGR000001781852129187', None, '2026-06-19 07:55:29', '2026-06-19 07:55:29'
))

cur.execute('UPDATE palety_agro SET status="w_magazynie" WHERE id=%s', (p_id,))
c.commit()
print("Fixed single pallet")
