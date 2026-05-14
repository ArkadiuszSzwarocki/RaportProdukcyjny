from app.db import get_db_connection
try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT linia, COUNT(*) as ile FROM magazyn_opakowania GROUP BY linia')
    print('Wartosci kolumny linia:', cur.fetchall())
except Exception as e:
    print('Blad:', e)

