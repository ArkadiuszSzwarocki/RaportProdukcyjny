from app.db import get_db_connection


# Tank definitions per group
ZBIORNIKI_BB_MZ = (
    [f'BB{str(i).zfill(2)}' for i in range(1, 7)]
    + [f'BB{str(i).zfill(2)}' for i in range(11, 23)]
    + [f'MZ{str(i).zfill(2)}' for i in range(7, 11)]
    + ['MZ23', 'MZ24']
)

ZBIORNIKI_KO = [f'KO{str(i).zfill(2)}' for i in range(1, 23)]

ZBIORNIKI_MAP = {
    'BB_MZ': ZBIORNIKI_BB_MZ,
    'KO': ZBIORNIKI_KO,
}


class InwentaryzacjaProdukcjiService:

    @staticmethod
    def get_tanks_for_type(typ):
        return ZBIORNIKI_MAP.get(typ, [])

    @staticmethod
    def get_active_sessions():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM produkcja_inwentaryzacja_sesje WHERE status = 'OPEN' ORDER BY created_at DESC"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def start_session(typ, user_login, comment=''):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO produkcja_inwentaryzacja_sesje (typ, created_by, comment) VALUES (%s, %s, %s)",
                (typ, user_login, comment)
            )
            conn.commit()
            return True, cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM produkcja_inwentaryzacja_sesje WHERE id = %s", (sesja_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def get_tanks_status(sesja_id, typ):
        tanks = InwentaryzacjaProdukcjiService.get_tanks_for_type(typ)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM produkcja_inwentaryzacja_wpisy WHERE sesja_id = %s",
                (sesja_id,)
            )
            entries = cursor.fetchall()

            entries_map = {}
            for e in entries:
                entries_map[e['zbiornik']] = e

            result = []
            for tank in tanks:
                entry = entries_map.get(tank)
                result.append({
                    'zbiornik': tank,
                    'counted': entry is not None,
                    'nazwa': entry['nazwa'] if entry else '',
                    'nr_partii': entry['nr_partii'] if entry else '',
                    'waga': float(entry['waga']) if entry and entry['waga'] is not None else None,
                    'komentarz': entry['komentarz'] if entry else '',
                    'user_login': entry['user_login'] if entry else '',
                    'data_wpisu': entry['data_wpisu'] if entry else None,
                })
            return result
        finally:
            conn.close()

    @staticmethod
    def save_entry(sesja_id, zbiornik, nazwa, nr_partii, waga, komentarz, user_login):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT id FROM produkcja_inwentaryzacja_wpisy WHERE sesja_id = %s AND zbiornik = %s",
                (sesja_id, zbiornik)
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE produkcja_inwentaryzacja_wpisy SET nazwa = %s, nr_partii = %s, waga = %s, komentarz = %s, user_login = %s, data_wpisu = NOW() WHERE id = %s",
                    (nazwa, nr_partii, waga, komentarz, user_login, existing['id'])
                )
            else:
                cursor.execute(
                    "INSERT INTO produkcja_inwentaryzacja_wpisy (sesja_id, zbiornik, nazwa, nr_partii, waga, komentarz, user_login) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (sesja_id, zbiornik, nazwa, nr_partii, waga, komentarz, user_login)
                )

            conn.commit()
            return True, "Wpis zapisany"
        except Exception as e:
            if conn:
                conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    @staticmethod
    def get_report(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM produkcja_inwentaryzacja_wpisy WHERE sesja_id = %s ORDER BY zbiornik",
                (sesja_id,)
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def close_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE produkcja_inwentaryzacja_sesje SET status = 'CLOSED', closed_at = NOW() WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Sesja zamknięta"
        finally:
            conn.close()

    @staticmethod
    def resume_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE produkcja_inwentaryzacja_sesje SET status = 'OPEN', closed_at = NULL WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Sesja została wznowiona"
        finally:
            conn.close()

    @staticmethod
    def revert_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE produkcja_inwentaryzacja_sesje SET status = 'OPEN', closed_at = NULL WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Zatwierdzenie zostało wycofane. Sesja jest ponownie otwarta."
        finally:
            conn.close()

    @staticmethod
    def apply_inventory(sesja_id, user_login):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE produkcja_inwentaryzacja_sesje SET status = 'APPLIED', closed_at = NOW() WHERE id = %s",
                (sesja_id,)
            )
            conn.commit()
            return True, "Inwentaryzacja zatwierdzona"
        finally:
            conn.close()

    @staticmethod
    def delete_session(sesja_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM produkcja_inwentaryzacja_wpisy WHERE sesja_id = %s", (sesja_id,))
            cursor.execute("DELETE FROM produkcja_inwentaryzacja_sesje WHERE id = %s", (sesja_id,))
            conn.commit()
            return True, "Sesja została usunięta"
        except Exception as e:
            if conn:
                conn.rollback()
            return False, f"Błąd bazy danych: {str(e)}"
        finally:
            conn.close()

    @staticmethod
    def update_session(sesja_id, comment):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE produkcja_inwentaryzacja_sesje SET comment = %s WHERE id = %s",
                (comment, sesja_id)
            )
            conn.commit()
            return True, "Dane sesji zostały zaktualizowane"
        finally:
            conn.close()

    @staticmethod
    def get_all_product_names():
        conn = get_db_connection()
        names = set()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT nazwa FROM magazyn_surowce WHERE nazwa IS NOT NULL AND nazwa != ''")
            for r in cursor.fetchall():
                names.add(r[0])
            cursor.execute("SELECT DISTINCT nazwa FROM magazyn_opakowania WHERE nazwa IS NOT NULL AND nazwa != ''")
            for r in cursor.fetchall():
                names.add(r[0])
            cursor.execute("SELECT DISTINCT produkt FROM magazyn_palety WHERE produkt IS NOT NULL AND produkt != ''")
            for r in cursor.fetchall():
                names.add(r[0])
            cursor.execute("SELECT DISTINCT produkt FROM magazyn_palety_agro WHERE produkt IS NOT NULL AND produkt != ''")
            for r in cursor.fetchall():
                names.add(r[0])
            return sorted(list(names))
        except Exception:
            return []
        finally:
            conn.close()
