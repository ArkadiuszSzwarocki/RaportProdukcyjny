from app.db import get_db_connection

# IDs created during reproduction run
PLAN_ID = 1023
PALETA_ID = 836

conn = get_db_connection()
cur = conn.cursor()
try:
    cur.execute('DELETE FROM palety_workowanie WHERE id=%s', (PALETA_ID,))
    cur.execute('DELETE FROM plan_produkcji WHERE id=%s', (PLAN_ID,))
    conn.commit()
    print(f'Deleted paleta {PALETA_ID} and plan {PLAN_ID}')
except Exception as e:
    try:
        conn.rollback()
    except Exception:
        pass
    print('Error during cleanup:', e)
finally:
    try: cur.close()
    except Exception: pass
    try: conn.close()
    except Exception: pass
