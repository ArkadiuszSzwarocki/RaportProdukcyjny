from app.db import get_db_connection

def ensure_column(table_name, column_name, column_def):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SHOW COLUMNS FROM %s LIKE %s" % (table_name, "'%s'"%column_name))
        if cur.fetchone():
            print(f"Column {column_name} already exists in {table_name}")
            return
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        conn.commit()
        print(f"Added column {column_name} to {table_name}")
    except Exception as e:
        print('Error adding column', e)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    ensure_column('palety_workowanie', 'nr_palety_lp', 'INT NULL')
    ensure_column('magazyn_palety', 'nr_palety_lp', 'INT NULL')
