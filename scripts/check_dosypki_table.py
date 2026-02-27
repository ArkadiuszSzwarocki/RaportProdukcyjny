from app.db import get_db_connection

def main():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SHOW TABLES LIKE 'dosypki'")
        rows = cur.fetchall()
        print('FOUND:', rows)
    except Exception as e:
        print('ERROR:', e)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()
