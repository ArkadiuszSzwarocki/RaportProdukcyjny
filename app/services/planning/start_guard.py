"""Keep one unfinished production order per physical section."""


def get_unfinished_section_orders(cursor, table, section, *, lock=False):
    sections = ('Workowanie', 'Czyszczenie') if section in ('Workowanie', 'Czyszczenie') else (section,)
    placeholders = ','.join(['%s'] * len(sections))
    cursor.execute(f"SELECT id,produkt,status FROM {table} WHERE sekcja IN ({placeholders}) "
                   "AND COALESCE(is_deleted,0)=0 AND status IN ('w toku','zawieszone','wstrzymane') "
                   "ORDER BY id" + (" FOR UPDATE" if lock else ""), sections)
    return cursor.fetchall()


def guard_section_start(cursor, table, plan_id, section):
    orders = get_unfinished_section_orders(cursor, table, section, lock=True)
    is_resume = any(int(order_id) == int(plan_id) and status in ('zawieszone', 'wstrzymane')
                    for order_id, _product, status in orders)
    for other_id, product, status in orders:
        if int(other_id) != int(plan_id):
            if is_resume and status in ('zawieszone', 'wstrzymane'):
                continue
            if is_resume:
                return f'Nie można wznowić zlecenia: {product} (#{other_id}) jest w toku. Najpierw wstrzymaj albo zakończ działające zlecenie.'
            return f'Nie można rozpocząć innego zlecenia: {product} (#{other_id}) ma status {status}. Najpierw zakończ to zlecenie albo wznów właśnie je.'
    return None
