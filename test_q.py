from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
prefix = 'SUR080520268243385213'
skip_warehouse_lookup = False
linia = 'AGRO'
where_clause = '''(
    REPLACE(REPLACE(REPLACE(lokalizacja, '_', ''), '-', ''), ' ', '') LIKE %s OR
    nazwa LIKE %s OR
    COALESCE(nr_partii, '') LIKE %s OR
    COALESCE(nr_palety, '') LIKE %s OR
    CAST(id AS CHAR) = %s
)'''
clean_prefix = prefix.replace('_', '').replace('-', '').replace(' ', '')
like_prefix = f'{clean_prefix}%'
like_any = f'%{prefix}%'
params = [like_prefix, like_any, like_any, like_any, prefix]
q3 = f'''
    SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, 'dodatek' as type
    FROM magazyn_dodatki
    WHERE {'1=1' if skip_warehouse_lookup else 'stan_magazynowy > 0'} AND {where_clause} AND linia = %s
'''
cur.execute(q3, params + [linia])
res = cur.fetchall()
print(f'Length: {len(res)}')
if res:
    print(res[0])
