from app.db import get_db_connection

def verify():
    conn = get_db_connection()
    c = conn.cursor(dictionary=True)
    c.execute("SELECT id, typ_raportu, nazwa_raportu FROM przypisania_raportow")
    for r in c.fetchall():
        print(f"{r['id']} | {r['typ_raportu']} | {r['nazwa_raportu']}")
    conn.close()

if __name__ == '__main__':
    verify()
