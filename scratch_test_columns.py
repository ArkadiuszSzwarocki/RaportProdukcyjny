from app.db import get_db_connection

def test():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT jednostka FROM magazyn_surowce LIMIT 1")
        print("magazyn_surowce has jednostka")
    except Exception as e:
        print("magazyn_surowce:", e)
        
    try:
        cur.execute("SELECT jednostka FROM magazyn_opakowania LIMIT 1")
        print("magazyn_opakowania has jednostka")
    except Exception as e:
        print("magazyn_opakowania:", e)
        
    try:
        cur.execute("SELECT jednostka FROM palety_psd_magazyn LIMIT 1")
        print("palety_psd_magazyn has jednostka")
    except Exception as e:
        print("palety_psd_magazyn:", e)
        
    try:
        cur.execute("SELECT jednostka FROM magazyn_inwentaryzacja_wpisy LIMIT 1")
        print("magazyn_inwentaryzacja_wpisy has jednostka")
    except Exception as e:
        print("magazyn_inwentaryzacja_wpisy:", e)

    conn.close()

if __name__ == '__main__':
    test()
