from app.db import get_db_connection
from datetime import date

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    print('--- Users with role containing "labor" ---')
    try:
        cur.execute("SELECT id, login, rola, pracownik_id FROM uzytkownicy WHERE rola LIKE %s", ('%labor%',))
        for r in cur.fetchall():
            print(r)
    except Exception as e:
        print('Users query failed:', e)

    print('\n--- Distinct roles ---')
    try:
        cur.execute('SELECT DISTINCT rola FROM uzytkownicy')
        for r in cur.fetchall():
            print(r[0])
    except Exception as e:
        print('Distinct roles failed:', e)

    print('\n--- Zasyp plans for today ---')
    try:
        today = date.today()
        cur.execute("SELECT id, produkt, status FROM plan_produkcji WHERE sekcja='Zasyp' AND DATE(data_planu)=%s ORDER BY id", (today,))
        rows = cur.fetchall()
        if not rows:
            print('No Zasyp plans found for', today)
        else:
            for r in rows:
                print(r)
    except Exception as e:
        print('Zasyp query failed:', e)

    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
