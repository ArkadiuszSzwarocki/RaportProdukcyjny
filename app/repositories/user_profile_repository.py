"""
Repozytorium danych profilowych użytkownika.
Obsługuje zapytania SQL do tabel uzytkownicy, pracownicy i obecnosc.
"""
from typing import Optional
from app.core.database import get_db_connection
from app.models.user_profile_model import UserProfileModel



class UserProfileRepository:
    """Repozytorium do zarządzania danymi profilowymi użytkownika."""

    def get_by_user_id(self, user_id: int) -> Optional[UserProfileModel]:
        """Pobiera model profilu użytkownika na podstawie ID użytkownika."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT 
                    u.id as user_id, 
                    u.login, 
                    u.rola, 
                    COALESCE(u.grupa, '') as grupa, 
                    u.pracownik_id,
                    COALESCE(NULLIF(p.imie_nazwisko, ''), u.login) as imie_nazwisko,
                    COALESCE(NULLIF(u.email, ''), NULLIF(p.email, ''), '') as email,
                    COALESCE(p.urlop_biezacy, 0) as urlop_biezacy,
                    COALESCE(p.urlop_zalegly, 0) as urlop_zalegly
                FROM uzytkownicy u
                LEFT JOIN pracownicy p ON u.pracownik_id = p.id
                WHERE u.id = %s
                """,
                (user_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            used_days = self._get_used_leave_days_by_pracownik(cursor, row['pracownik_id'])

            return UserProfileModel(
                user_id=row['user_id'],
                login=row['login'],
                imie_nazwisko=row['imie_nazwisko'],
                rola=row['rola'],
                grupa=row['grupa'],
                email=row['email'],
                pracownik_id=row['pracownik_id'],
                urlop_biezacy=row['urlop_biezacy'],
                urlop_zalegly=row['urlop_zalegly'],
                urlop_wykorzystany=used_days
            )
        finally:
            conn.close()

    def get_by_login(self, login: str) -> Optional[UserProfileModel]:
        """Pobiera model profilu użytkownika na podstawie loginu."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT 
                    u.id as user_id, 
                    u.login, 
                    u.rola, 
                    COALESCE(u.grupa, '') as grupa, 
                    u.pracownik_id,
                    COALESCE(NULLIF(p.imie_nazwisko, ''), u.login) as imie_nazwisko,
                    COALESCE(NULLIF(u.email, ''), NULLIF(p.email, ''), '') as email,
                    COALESCE(p.urlop_biezacy, 0) as urlop_biezacy,
                    COALESCE(p.urlop_zalegly, 0) as urlop_zalegly
                FROM uzytkownicy u
                LEFT JOIN pracownicy p ON u.pracownik_id = p.id
                WHERE u.login = %s
                """,
                (login,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            used_days = self._get_used_leave_days_by_pracownik(cursor, row['pracownik_id'])

            return UserProfileModel(
                user_id=row['user_id'],
                login=row['login'],
                imie_nazwisko=row['imie_nazwisko'],
                rola=row['rola'],
                grupa=row['grupa'],
                email=row['email'],
                pracownik_id=row['pracownik_id'],
                urlop_biezacy=row['urlop_biezacy'],
                urlop_zalegly=row['urlop_zalegly'],
                urlop_wykorzystany=used_days
            )
        finally:
            conn.close()

    def update_profile(
        self,
        user_id: int,
        email: str,
        urlop_biezacy: int,
        urlop_zalegly: int,
        imie_nazwisko: Optional[str] = None
    ) -> bool:
        """Aktualizuje dane profilowe użytkownika w bazie."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # Aktualizacja email w uzytkownicy
            cursor.execute("UPDATE uzytkownicy SET email = %s WHERE id = %s", (email, user_id))

            # Sprawdzenie powiązanego pracownika
            cursor.execute("SELECT pracownik_id FROM uzytkownicy WHERE id = %s", (user_id,))
            user_row = cursor.fetchone()
            prac_id = user_row['pracownik_id'] if user_row else None

            if prac_id:
                if imie_nazwisko:
                    cursor.execute(
                        """
                        UPDATE pracownicy 
                        SET email = %s, urlop_biezacy = %s, urlop_zalegly = %s, imie_nazwisko = %s 
                        WHERE id = %s
                        """,
                        (email, urlop_biezacy, urlop_zalegly, imie_nazwisko, prac_id)
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE pracownicy 
                        SET email = %s, urlop_biezacy = %s, urlop_zalegly = %s 
                        WHERE id = %s
                        """,
                        (email, urlop_biezacy, urlop_zalegly, prac_id)
                    )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get_used_leave_days_by_pracownik(self, cursor, pracownik_id: Optional[int]) -> int:
        """Pobiera sumaryczną liczbę wykorzystanych dni urlopu w bieżącym roku."""
        if not pracownik_id:
            return 0
        try:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT data_wpisu) as days
                FROM obecnosc
                WHERE pracownik_id = %s 
                  AND LOWER(typ) LIKE '%urlop%' 
                  AND YEAR(data_wpisu) = YEAR(CURDATE())
                """,
                (pracownik_id,)
            )
            res = cursor.fetchone()
            return int(res['days']) if res and res['days'] else 0
        except Exception:
            return 0
