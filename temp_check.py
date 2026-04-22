from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT login, rola, grupa FROM uzytkownicy WHERE rola='magazynier'")
    rows = cursor.fetchall()
    print("Magazynierzy:")
    for r in rows:
        print(f" - {r['login']} (Grupa: {r['grupa']})")
    
    cursor.execute("SELECT login, rola, grupa FROM uzytkownicy WHERE login='magazynier'")
    rows = cursor.fetchall()
    if rows:
        print("Specjalny user 'magazynier':")
        for r in rows:
            print(f" - {r['login']} (Grupa: {r['grupa']})")
    
    conn.close()

if __name__ == '__main__':
    main()
