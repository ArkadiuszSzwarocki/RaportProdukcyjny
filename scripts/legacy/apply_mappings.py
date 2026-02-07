import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db

def apply_mappings(mappings):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    try:
        for login, pid in mappings.items():
            cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (pid, login))
            print(f"{login} -> {pid}: rows={cursor.rowcount}")
        conn.commit()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    mappings = {
        "BanasPio": 19,
        "LuberBar": 13,
        "KwiatFil": 14,
        "JabloArt": 15,
        "BudzaMat": 18,
        "BurzyMat": 12,
        "HelleAnd": 16,
        "WarzyJan": 17,
        "PawloAne": 9,
        "StempPio": 10,
        "BoczkMar": 11,
        "StefAnna": 20,
    }
    apply_mappings(mappings)
