"""
List `uzytkownicy` and `pracownicy` to help assign `pracownik_id` mappings.
Usage: python scripts\list_mappings.py
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from db import get_db_connection

def list_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    print('Uzytkownicy: id | login | pracownik_id')
    cursor.execute('SELECT id, login, COALESCE(pracownik_id, NULL) FROM uzytkownicy ORDER BY id')
    for r in cursor.fetchall():
        print(r[0], '|', r[1], '|', r[2])
    print('\nPracownicy: id | imie_nazwisko')
    cursor.execute('SELECT id, imie_nazwisko FROM pracownicy ORDER BY id')
    for r in cursor.fetchall():
        print(r[0], '|', r[1])
    conn.close()

if __name__ == '__main__':
    list_tables()
