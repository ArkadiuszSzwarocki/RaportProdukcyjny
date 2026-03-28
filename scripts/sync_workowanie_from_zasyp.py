import os
import sys
# Ensure repo root is on sys.path when running the script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.db import get_db_connection


def sync_workowanie():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Update Workowanie.tonaz to match Zasyp.tonaz_rzeczywisty for linked pairs
        cur.execute("""
            UPDATE plan_produkcji w
            JOIN plan_produkcji z ON w.zasyp_id = z.id
            SET w.tonaz = COALESCE(z.tonaz_rzeczywisty, 0)
            WHERE LOWER(w.sekcja) = 'workowanie' AND LOWER(z.sekcja) = 'zasyp'
              AND COALESCE(w.tonaz, 0) != COALESCE(z.tonaz_rzeczywisty, 0)
        """)
        updated = cur.rowcount
        conn.commit()
        print(f"[sync_workowanie] Updated {updated} Workowanie rows to match Zasyp.tonaz_rzeczywisty")
    except Exception as e:
        print(f"[sync_workowanie] ERROR: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()

if __name__ == '__main__':
    sync_workowanie()
