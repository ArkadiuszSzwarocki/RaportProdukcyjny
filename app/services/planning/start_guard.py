"""Keep one unfinished production order per physical section."""


def guard_section_start(cursor, table, plan_id, section):
    sections = ('Workowanie', 'Czyszczenie') if section in ('Workowanie', 'Czyszczenie') else (section,)
    placeholders = ','.join(['%s'] * len(sections))
    cursor.execute(f"SELECT id,produkt,status FROM {table} WHERE sekcja IN ({placeholders}) "
                   "AND COALESCE(is_deleted,0)=0 AND status IN ('w toku','zawieszone','wstrzymane') "
                   "ORDER BY id FOR UPDATE", sections)
    for other_id, product, status in cursor.fetchall():
        if int(other_id) != int(plan_id):
            return f'Nie można rozpocząć innego zlecenia: {product} (#{other_id}) ma status {status}. Najpierw zakończ to zlecenie albo wznów właśnie je.'
    return None
