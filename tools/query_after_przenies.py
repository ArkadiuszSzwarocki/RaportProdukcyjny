"""Query DB after running przenies_niezrealizowane for verification.

Usage:
  python tools/query_after_przenies.py 2026-03-30
If no date provided, defaults to next day from today.
"""
import sys
from app.core.factory import create_app
from app.db import get_db_connection
from datetime import date, timedelta

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else (date.today() + timedelta(days=1)).isoformat()
    app = create_app()
    with app.app_context():
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        print(f"Querying plan_produkcji for date: {date_arg}")
        cur.execute("""
            SELECT id, produkt, sekcja, tonaz, tonaz_rzeczywisty, status, zasyp_id
            FROM plan_produkcji
            WHERE data_planu = %s
            ORDER BY id DESC
            LIMIT 50
        """, (date_arg,))
        plans = cur.fetchall()
        for p in plans:
            print(p)

        print(f"\nQuerying bufor for date: {date_arg}")
        cur.execute("""
            SELECT id, zasyp_id, produkt, data_planu, tonaz_rzeczywisty, spakowano, kolejka, status
            FROM bufor
            WHERE data_planu = %s
            ORDER BY kolejka ASC
        """, (date_arg,))
        bufor_rows = cur.fetchall()
        for b in bufor_rows:
            print(b)

        cur.close()
        conn.close()
