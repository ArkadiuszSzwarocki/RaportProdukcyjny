from app.db import get_db_connection

def get_table_name(base_name, linia):
    """Helper dla nazw tabel z suffiksem linii."""
    linia_lower = str(linia).lower()
    return f"{base_name}_{linia_lower}"

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

# Test query dla wyrobów gotowych
table_wg = get_table_name('magazyn_palety', 'AGRO')
print(f'Tabela wyrobów gotowych: {table_wg}')

# Pobierz 3 przykładowe rekordy
cur.execute(f"""
    SELECT id, nr_palety, produkt, waga_netto, 
           COALESCE(lokalizacja, 'MGW01') as lokalizacja, 
           nr_partii, data_produkcji
    FROM {table_wg}
    WHERE COALESCE(waga_netto, 0) > 0
    LIMIT 3
""")

rows = cur.fetchall()
print(f'\nZnaleziono {len(rows)} wyrobów gotowych:')
for r in rows:
    print(f'  - ID: {r["id"]}, Paleta: {r["nr_palety"]}, Produkt: {r["produkt"]}, Waga: {r["waga_netto"]} kg, Lokalizacja: {r["lokalizacja"]}')

# Test wyszukiwania po kodzie SSCC
test_code = 'AGR220420266849278003'
print(f'\n\nTest wyszukiwania kodu: {test_code}')

where_clause = """(
    REPLACE(REPLACE(REPLACE(COALESCE(lokalizacja, 'MGW01'), '_', ''), '-', ''), ' ', '') LIKE %s OR
    produkt LIKE %s OR
    COALESCE(nr_partii, '') LIKE %s OR
    COALESCE(nr_palety, '') LIKE %s OR
    CAST(id AS CHAR) = %s
)"""

clean_prefix = test_code.replace('_', '').replace('-', '').replace(' ', '')
like_prefix = f"{clean_prefix}%"
like_any = f"%{test_code}%"
params = [like_prefix, like_any, like_any, like_any, test_code]

q = f"""
    SELECT id, nr_palety, produkt as nazwa, waga_netto as stan_magazynowy, 
           COALESCE(lokalizacja, 'MGW01') as lokalizacja, nr_partii, 
           data_produkcji, data_przydatnosci
    FROM {table_wg}
    WHERE COALESCE(waga_netto, 0) > 0 AND {where_clause}
    LIMIT 5
"""

cur.execute(q, params)
results = cur.fetchall()
print(f'Wyniki dla "{test_code}": {len(results)} palet')
for r in results:
    print(f'  - {r["nr_palety"]}: {r["nazwa"]} ({r["stan_magazynowy"]} kg) @ {r["lokalizacja"]}')

conn.close()
print('\n✅ Test zakończony')
