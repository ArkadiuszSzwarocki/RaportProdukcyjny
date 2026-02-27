from app.db import get_db_connection

def check_user():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT login, rola FROM uzytkownicy WHERE login = 'HelleAnd'")
    res = cursor.fetchone()
    if res:
        print(f"User found: Login='{res[0]}', Rola='{res[1]}'")
    else:
        print("User HelleAnd not found in DB.")
        cursor.execute("SELECT login, rola FROM uzytkownicy LIMIT 10")
        print("Sample users:", cursor.fetchall())
    conn.close()

if __name__ == '__main__':
    check_user()
