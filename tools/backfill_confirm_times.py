"""
Backfill utility to normalize confirmation times.

- Dry run (default): shows counts and sample rows that would be updated.
- --apply: perform updates (wrapped in a transaction).

Actions performed:
1) Update `palety_workowanie.czas_rzeczywistego_potwierdzenia` to TIME(data_potwierdzenia)
   for rows where `data_potwierdzenia` is present but `czas_rzeczywistego_potwierdzenia` is NULL
   or differs from TIME(data_potwierdzenia).
2) Populate `magazyn_palety.data_potwierdzenia` from `palety_workowanie.data_potwierdzenia`
   when `magazyn_palety.data_potwierdzenia` IS NULL and `paleta_workowanie_id` links to a row
   with non-null `data_potwierdzenia`.

Usage:
  python tools/backfill_confirm_times.py         # dry run
  python tools/backfill_confirm_times.py --apply # actually apply changes
  python tools/backfill_confirm_times.py --limit 100 # limit samples/updates

Make a DB backup before running with --apply in production.
"""

import argparse
import os
import sys

# Ensure project root is on sys.path so `from app...` imports work when script
# is executed directly (e.g., in PowerShell). This makes the script runnable
# without requiring the caller to set PYTHONPATH.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.db import get_db_connection


def preview_and_apply(limit=10, apply=False):
    conn = get_db_connection()
    cur = conn.cursor()

    # 1) palety_workowanie: find rows needing normalization
    query_need_pw = (
        "SELECT COUNT(1) FROM palety_workowanie "
        "WHERE data_potwierdzenia IS NOT NULL "
        "AND (czas_rzeczywistego_potwierdzenia IS NULL OR TIME(data_potwierdzenia) != czas_rzeczywistego_potwierdzenia)"
    )
    cur.execute(query_need_pw)
    need_pw_count = cur.fetchone()[0]

    print(f"palety_workowanie rows needing czas_rzeczywistego_potwierdzenia fix: {need_pw_count}")

    if need_pw_count:
        cur.execute(
            "SELECT id, data_dodania, data_potwierdzenia, czas_rzeczywistego_potwierdzenia, TIME(data_potwierdzenia) AS desired_time "
            "FROM palety_workowanie "
            "WHERE data_potwierdzenia IS NOT NULL "
            "AND (czas_rzeczywistego_potwierdzenia IS NULL OR TIME(data_potwierdzenia) != czas_rzeczywistego_potwierdzenia) "
            "ORDER BY data_potwierdzenia DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        print("Sample palety_workowanie rows (id, data_dodania, data_potwierdzenia, czas_rzeczywistego_potwierdzenia, desired_time):")
        for r in rows:
            print(r)

    # 2) magazyn_palety: missing data_potwierdzenia
    query_need_m = (
        "SELECT COUNT(1) FROM magazyn_palety m "
        "JOIN palety_workowanie pw ON m.paleta_workowanie_id = pw.id "
        "WHERE m.data_potwierdzenia IS NULL AND pw.data_potwierdzenia IS NOT NULL"
    )
    cur.execute(query_need_m)
    need_m_count = cur.fetchone()[0]
    print(f"magazyn_palety rows needing data_potwierdzenia fill: {need_m_count}")

    if need_m_count:
        cur.execute(
            "SELECT m.id, m.paleta_workowanie_id, m.data_potwierdzenia, pw.data_potwierdzenia "
            "FROM magazyn_palety m JOIN palety_workowanie pw ON m.paleta_workowanie_id = pw.id "
            "WHERE m.data_potwierdzenia IS NULL AND pw.data_potwierdzenia IS NOT NULL "
            "ORDER BY pw.data_potwierdzenia DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        print("Sample magazyn_palety rows (m.id, paleta_workowanie_id, m.data_potwierdzenia, pw.data_potwierdzenia):")
        for r in rows:
            print(r)

    if not apply:
        print('\nDry run mode - no changes applied.')
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
        return {
            'palety_workowanie_need': need_pw_count,
            'magazyn_palety_need': need_m_count
        }

    # Apply updates
    try:
        print('\nApplying updates...')
        # Update palety_workowanie
        update_pw_sql = (
            "UPDATE palety_workowanie SET czas_rzeczywistego_potwierdzenia = TIME(data_potwierdzenia) "
            "WHERE data_potwierdzenia IS NOT NULL "
            "AND (czas_rzeczywistego_potwierdzenia IS NULL OR TIME(data_potwierdzenia) != czas_rzeczywistego_potwierdzenia)"
        )
        cur.execute(update_pw_sql)
        pw_updated = cur.rowcount
        print(f"palety_workowanie rows updated: {pw_updated}")

        # Update magazyn_palety
        update_m_sql = (
            "UPDATE magazyn_palety m JOIN palety_workowanie pw ON m.paleta_workowanie_id = pw.id "
            "SET m.data_potwierdzenia = pw.data_potwierdzenia "
            "WHERE m.data_potwierdzenia IS NULL AND pw.data_potwierdzenia IS NOT NULL"
        )
        cur.execute(update_m_sql)
        m_updated = cur.rowcount
        print(f"magazyn_palety rows updated: {m_updated}")

        conn.commit()
        print('Apply committed.')
    except Exception as e:
        print('Error during apply:', e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

    return {
        'palety_workowanie_updated': pw_updated,
        'magazyn_palety_updated': m_updated
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill/normalize confirmation times')
    parser.add_argument('--apply', action='store_true', help='Apply changes to DB')
    parser.add_argument('--limit', type=int, default=10, help='Limit sample rows shown')
    args = parser.parse_args()

    res = preview_and_apply(limit=args.limit, apply=args.apply)
    # If desired, we could write res to a JSON file or similar for logging
    
