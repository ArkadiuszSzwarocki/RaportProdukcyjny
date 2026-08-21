import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.db import get_db_connection
from datetime import date


def query_incomplete(wybrana_data=None):
    wybrana_data = wybrana_data or str(date.today())
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = '''
        SELECT id, sekcja, produkt, tonaz, COALESCE(tonaz_rzeczywisty, 0) as tonaz_rz,
               (COALESCE(tonaz,0) - COALESCE(tonaz_rzeczywisty,0)) as remaining
        FROM plan_produkcji
        WHERE DATE(data_planu) = %s AND status = 'zakonczone' AND COALESCE(tonaz,0) > COALESCE(tonaz_rzeczywisty,0)
        ORDER BY remaining DESC
    '''
    cursor.execute(sql, (wybrana_data,))
    rows = cursor.fetchall()
    if not rows:
        print(f'No incomplete plans found for date {wybrana_data}')
    else:
        print(f'Incomplete plans for {wybrana_data}:')
        print('id | sekcja | produkt | plan(kg) | wykon(kg) | remaining(kg)')
        for r in rows:
            print(f'{r[0]:5} | {r[1]:6} | {r[2]:30} | {r[3]:8.1f} | {r[4]:8.1f} | {r[5]:8.1f}')
    cursor.close()
    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', '-d', help='Date to check (YYYY-MM-DD)', default=None)
    args = parser.parse_args()
    query_incomplete(args.date)
