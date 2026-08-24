"""
Serwis biznesowy dla profilu użytkownika.
Zawiera logikę biznesową i walidacje dla danych profilowych i ustawień osobistych.
"""
import re
from typing import Optional, Tuple
from app.repositories.user_profile_repository import UserProfileRepository
from app.dto.user_profile_dto import UserProfileDTO, UserProfileUpdateDTO


class UserProfileService:
    """Serwis obsługujący profil użytkownika i ustawienia osobiste."""

    def __init__(self, repository: Optional[UserProfileRepository] = None):
        self.repository = repository or UserProfileRepository()

    def get_user_profile(self, user_id: Optional[int] = None, login: Optional[str] = None) -> Optional[UserProfileDTO]:
        """Pobiera dane profilowe użytkownika i pakuje do DTO."""
        if user_id:
            model = self.repository.get_by_user_id(user_id)
        elif login:
            model = self.repository.get_by_login(login)
        else:
            return None

        if not model:
            return None

        laczny_urlop = (model.urlop_biezacy or 0) + (model.urlop_zalegly or 0)

        return UserProfileDTO(
            user_id=model.user_id,
            login=model.login,
            imie_nazwisko=model.imie_nazwisko,
            rola=model.rola,
            grupa=model.grupa,
            email=model.email or "",
            pracownik_id=model.pracownik_id,
            urlop_biezacy=model.urlop_biezacy or 0,
            urlop_zalegly=model.urlop_zalegly or 0,
            urlop_wykorzystany=model.urlop_wykorzystany or 0,
            urlop_laczny=laczny_urlop
        )

    def update_user_profile(self, user_id: int, update_dto: UserProfileUpdateDTO) -> Tuple[bool, str]:
        """Waliduje oraz aktualizuje dane profilowe użytkownika."""
        current_profile = self.repository.get_by_user_id(user_id)
        if not current_profile:
            return False, "Nie odnaleziono konta użytkownika."

        email = (update_dto.email if update_dto.email is not None else current_profile.email).strip()
        if email:
            email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
            if not re.match(email_pattern, email):
                return False, "Podany adres e-mail jest nieprawidłowy."

        urlop_biezacy = update_dto.urlop_biezacy if update_dto.urlop_biezacy is not None else current_profile.urlop_biezacy
        urlop_zalegly = update_dto.urlop_zalegly if update_dto.urlop_zalegly is not None else current_profile.urlop_zalegly

        if urlop_biezacy < 0 or urlop_zalegly < 0:
            return False, "Liczba dni urlopu nie może być ujemna."

        imie_nazwisko = update_dto.imie_nazwisko if update_dto.imie_nazwisko is not None else current_profile.imie_nazwisko

        try:
            self.repository.update_profile(
                user_id=user_id,
                email=email,
                urlop_biezacy=urlop_biezacy,
                urlop_zalegly=urlop_zalegly,
                imie_nazwisko=imie_nazwisko
            )
            return True, "Profil użytkownika został pomyślnie zaktualizowany."
        except Exception as e:
            return False, f"Błąd podczas zapisu w bazie danych: {str(e)}"
