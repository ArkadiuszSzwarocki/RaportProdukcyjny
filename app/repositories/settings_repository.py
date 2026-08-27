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
            cur.execute("SELECT id, nazwa, ip, lokalizacja, typ_drukarki FROM drukarki WHERE aktywna = 1 ORDER BY id ASC")
            return cur.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def get_printer_by_id(printer_id: int):
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, nazwa, ip, lokalizacja, typ_drukarki FROM drukarki WHERE id = %s AND aktywna = 1", (printer_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_default_printer_for_line(linia: str = 'AGRO'):
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            linia_clean = str(linia or '').strip().upper()
            if linia_clean == 'AGRO':
                cur.execute("""
                    SELECT id, nazwa, ip, lokalizacja, typ_drukarki
                    FROM drukarki
                    WHERE aktywna = 1
                    ORDER BY
                        CASE
                            WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%agro%' THEN 0
                            WHEN LOWER(COALESCE(nazwa, '')) LIKE '%agro%' THEN 1
                            WHEN LOWER(COALESCE(nazwa, '')) LIKE '%produkcja%' THEN 2
                            ELSE 3
                        END,
                        id ASC
                    LIMIT 1
                """)
            else:
                cur.execute("""
                    SELECT id, nazwa, ip, lokalizacja, typ_drukarki
                    FROM drukarki
                    WHERE aktywna = 1
                    ORDER BY
                        CASE
                            WHEN LOWER(COALESCE(nazwa, '')) LIKE '%psd%' THEN 0
                            WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%magazyn%' THEN 1
                            ELSE 2
                        END,
                        id ASC
                    LIMIT 1
                """)
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT id, nazwa, ip, lokalizacja, typ_drukarki FROM drukarki WHERE aktywna = 1 ORDER BY id ASC LIMIT 1")
                row = cur.fetchone()
            return row
        finally:
            conn.close()

