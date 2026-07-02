from app.db import get_table_name, get_db_connection
from app.utils.pallet_id import generate_pallet_id
from datetime import datetime
from app.services.print_server import get_printer

def preprint_labels(plan_id, count, linia='PSD', user_login='System', auto_print=False):
    """Reserve `count` pallet slots for `plan_id`.

    Optional auto-print can be enabled with `auto_print=True`.

    Returns list of created records: [{'id': ..., 'nr_palety': ...}, ...]
    """
    conn = get_db_connection()
    cur = conn.cursor()
    table_pal = get_table_name('palety_workowanie', linia)
    table_plan = get_table_name('plan_produkcji', linia)
    created = []
    now_ts = datetime.now()
    plan_display_name = None

    try:
        cur.execute(f"SELECT nazwa_zlecenia, produkt FROM {table_plan} WHERE id = %s", (plan_id,))
        plan_row = cur.fetchone()
        if plan_row:
            if isinstance(plan_row, (list, tuple)):
                raw_name = plan_row[0] if len(plan_row) > 0 else None
                raw_product = plan_row[1] if len(plan_row) > 1 else None
            else:
                raw_name = (plan_row.get('nazwa_zlecenia') if hasattr(plan_row, 'get') else None)
                raw_product = (plan_row.get('produkt') if hasattr(plan_row, 'get') else None)
            plan_display_name = str(raw_name or raw_product or '').strip() or None
    except Exception:
        plan_display_name = None

    if not plan_display_name:
        plan_display_name = f"PLAN-{plan_id}"

    try:
        for i in range(int(count)):
            nr_palety = generate_pallet_id(linia)
            # insert reserved row with zero weight and status 'rezerwacja'
            cur.execute(
                f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety) VALUES (%s, %s, 25, 0, %s, 'rezerwacja', %s, %s)",
                (plan_id, 0, now_ts, user_login, nr_palety),
            )
            pid = cur.lastrowid if hasattr(cur, 'lastrowid') else None
            # compute nr_palety_lp
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, pid))
                res = cur.fetchone()
                nr_palety_lp = int(res[0]) if res else None
                # update if column exists
                try:
                    cur.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                    if cur.fetchone():
                        cur.execute(f"UPDATE {table_pal} SET nr_palety_lp = %s WHERE id = %s", (nr_palety_lp, pid))
                except Exception:
                    pass
            except Exception:
                nr_palety_lp = None

            created.append({
                'id': pid,
                'plan_id': plan_id,
                'nr_palety': nr_palety,
                'nr_palety_lp': nr_palety_lp,
                'nazwa_zlecenia': plan_display_name,
            })

        conn.commit()

        if auto_print:
            # Trigger printing (best-effort) only when explicitly requested.
            try:
                printer = get_printer()
                for rec in created:
                    try:
                        from app.utils.pallet_label import prepare_pallet_label_data
                        conn2 = get_db_connection()
                        cur2 = conn2.cursor()
                        label_data = prepare_pallet_label_data(cur2, rec['id'], linia, source_table='workowanie')
                        cur2.close(); conn2.close()
                        if label_data:
                            printer.print_finished_product_label(label_data)
                    except Exception:
                        pass
            except Exception:
                pass

        return created
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
