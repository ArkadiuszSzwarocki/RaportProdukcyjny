from app.db import get_db_connection

class SettingsRepository:
    @staticmethod
    def get_allowed_locations():
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM magazyn_dozwolone_lokalizacje ORDER BY nazwa ASC")
            return cur.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def add_allowed_location(nazwa: str, opis: str):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO magazyn_dozwolone_lokalizacje (nazwa, opis) VALUES (%s, %s)", (nazwa, opis))
            conn.commit()
            return True, "Lokalizacja dodana pomyślnie."
        except Exception as e:
            conn.rollback()
            if 'Duplicate entry' in str(e):
                return False, "Taka lokalizacja już istnieje."
            raise e
        finally:
            conn.close()

    @staticmethod
    def delete_allowed_location(loc_id: int):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM magazyn_dozwolone_lokalizacje WHERE id = %s", (loc_id,))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_active_printers():
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1 ORDER BY id ASC")
            return cur.fetchall() or []
        finally:
            conn.close()
