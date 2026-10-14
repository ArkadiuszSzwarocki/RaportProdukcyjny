"""Read active pallets matching the last six digits without picking a winner."""
import re

from app.db import get_db_connection, get_table_name


def find_pallet_suggestions(digits):
    if not re.fullmatch(r'[0-9]{6}', str(digits or '')):
        return []
    sources = (
        ('magazyn_surowce', 'nazwa', 'stan_magazynowy', 'Surowiec'),
        ('magazyn_opakowania', 'nazwa', 'stan_magazynowy', 'Opakowanie'),
        ('magazyn_dodatki', 'nazwa', 'stan_magazynowy', 'Dodatek'),
        ('magazyn_palety', 'produkt', 'waga_netto', 'Wyrób Gotowy'),
    )
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        results, visited = [], set()
        for line in ('PSD', 'AGRO', 'OSIP'):
            for base, name, qty, kind in sources:
                table = get_table_name(base, line)
                if table in visited:
                    continue
                visited.add(table)
                cursor.execute(
                    f"SELECT id, nr_palety, {name} AS nazwa, {qty} AS ilosc, lokalizacja, "
                    f"COALESCE(NULLIF(linia, ''), %s) AS linia FROM {table} "
                    f"WHERE nr_palety LIKE %s AND COALESCE({qty}, 0)>0 ORDER BY nr_palety, id LIMIT 30",
                    (line, '%' + digits),
                )
                for row in cursor.fetchall():
                    row['inventory_type'] = kind
                    row['ilosc'] = float(row['ilosc'])
                    results.append(row)
        return results
    finally:
        conn.close()
