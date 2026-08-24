"""
Testy jednostkowe dla UserProfileService i UserProfileRepository.
"""
from unittest.mock import MagicMock
from app.services.user_profile_service import UserProfileService
from app.models.user_profile_model import UserProfileModel
from app.dto.user_profile_dto import UserProfileUpdateDTO


def test_get_user_profile_returns_dto():
    mock_repo = MagicMock()
    mock_repo.get_by_login.return_value = UserProfileModel(
        user_id=1,
        login="testuser",
        imie_nazwisko="Jan Kowalski",
        rola="admin",
        grupa="Biuro",
        email="jan@example.com",
        pracownik_id=10,
        urlop_biezacy=20,
        urlop_zalegly=5,
        urlop_wykorzystany=2
    )

    service = UserProfileService(repository=mock_repo)
    dto = service.get_user_profile(login="testuser")

    assert dto is not None
    assert dto.user_id == 1
    assert dto.login == "testuser"
    assert dto.imie_nazwisko == "Jan Kowalski"
    assert dto.email == "jan@example.com"
    assert dto.urlop_biezacy == 20
    assert dto.urlop_zalegly == 5
    assert dto.urlop_laczny == 25
    assert dto.urlop_wykorzystany == 2


def test_update_user_profile_validates_email():
    mock_repo = MagicMock()
    mock_repo.get_by_user_id.return_value = UserProfileModel(
        user_id=1,
        login="testuser",
        imie_nazwisko="Jan Kowalski",
        rola="admin",
        grupa="Biuro"
    )

    service = UserProfileService(repository=mock_repo)

    # Invalid email test
    update_dto = UserProfileUpdateDTO(email="invalid-email-address")
    success, msg = service.update_user_profile(1, update_dto)
    assert success is False
    assert "nieprawidłowy" in msg

    # Valid email test
    update_dto_valid = UserProfileUpdateDTO(email="jan.kowalski@wp.pl", urlop_biezacy=26, urlop_zalegly=0)
    success_valid, msg_valid = service.update_user_profile(1, update_dto_valid)
    assert success_valid is True
    mock_repo.update_profile.assert_called_once()
