import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nazwa, stan_magazynowy, lokalizacja, linia FROM magazyn_opakowania")
    rows = cursor.fetchall()
    print(f"Total rows: {len(rows)}")
    for r in rows:
        nazwa = r['nazwa'].encode('utf-8', errors='ignore').decode('utf-8')
        print(f"ID: {r['id']}, Nazwa: {nazwa}, Stan: {r['stan_magazynowy']}, Lokalizacja: {r['lokalizacja']}, Linia: {r['linia']}")
    conn.close()

if __name__ == '__main__':
    main()
