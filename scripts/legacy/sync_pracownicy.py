import os
import sys

# Ensure repository root is on sys.path so imports like `db` and `config` work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import get_db_connection


def main():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM uzytkownicy")
    uzytk_ids = set(r[0] for r in cursor.fetchall())

    cursor.execute("SELECT id FROM pracownicy")
    prac_ids = set(r[0] for r in cursor.fetchall())

    missing = sorted(uzytk_ids - prac_ids)

    if not missing:
        print("Brak brakujących ID do wstawienia.")
    else:
        print(f"Znaleziono {len(missing)} brakujących ID: {missing}")
        for mid in missing:
            try:
                cursor.execute("INSERT INTO pracownicy (id, imie_nazwisko) VALUES (%s, %s)", (mid, ''))
                print(f"Wstawiono pracownik id={mid}")
            except Exception as e:
                print(f"Nie udało się wstawić id={mid}: {e}")
        conn.commit()

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
