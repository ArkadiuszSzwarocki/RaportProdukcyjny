import sqlite3

def check_user():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT rola FROM users WHERE login = 'HelleAnd'")
    res = cursor.fetchone()
    if res:
        print(f"HelleAnd rola: '{res[0]}'")
    else:
        print("User HelleAnd not found.")
    conn.close()

if __name__ == '__main__':
    check_user()
