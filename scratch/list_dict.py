from app.db import get_db_connection

def list_dict():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM magazyn_agro_slownik_surowce ORDER BY nazwa")
    rows = cursor.fetchall()
    for r in rows:
        print(f"{r['id']}: {r['nazwa']}")
    conn.close()

if __name__ == "__main__":
    list_dict()
