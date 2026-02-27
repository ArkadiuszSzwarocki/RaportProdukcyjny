from app.db import get_db_connection


def main():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT login, rola, pracownik_id FROM uzytkownicy WHERE login IN ('hellerand','helleand') OR login LIKE 'heller%'")
        rows = cur.fetchall()
        if not rows:
            print('--- no rows ---')
        else:
            for r in rows:
                print(r)
    except Exception as e:
        print('ERROR', e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
