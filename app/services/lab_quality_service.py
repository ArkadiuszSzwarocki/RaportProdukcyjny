from typing import Dict, Any, List, Optional, Tuple
from app.repositories.lab_quality_repository import LabQualityRepository
from app.dto.service_result import ServiceResult

class LabQualityService:
    """
    Domain service managing Quality Control Laboratory Holds (Blokada LAB) and QA Releases.
    Enforces quality restrictions and prevents consumption/dispatch of unapproved materials.
    """

    @staticmethod
    def block_pallet_by_lab(
        pallet_id: int,
        pallet_code: str,
        pallet_type: str = 'surowiec',
        linia: str = 'PSD',
        reason: str = '',
        user_login: str = 'system'
    ) -> ServiceResult:
        """
        Applies a LAB hold to a pallet/raw material.
        """
        if not pallet_code:
            return ServiceResult.fail("Brak kodu palety do zablokowania.")

        block_id = LabQualityRepository.block_pallet_in_lab(
            pallet_id=pallet_id,
            pallet_code=pallet_code,
            pallet_type=pallet_type,
            linia=linia,
            reason=reason or "Blokada kontrolna Działu Jakości (LAB)",
            user_login=user_login
        )

        return ServiceResult.ok(
            data={"block_id": block_id, "pallet_code": pallet_code, "status": "BLOKADA_LAB"},
            message=f"Paleta {pallet_code} została zablokowana przez LAB."
        )

    @staticmethod
    def release_pallet_by_lab(
        pallet_code: str,
        pallet_type: str = 'surowiec',
        linia: str = 'PSD',
        user_login: str = 'system',
        comment: str = ''
    ) -> ServiceResult:
        """
        Releases a pallet from LAB hold after positive laboratory results.
        """
        if not pallet_code:
            return ServiceResult.fail("Brak kodu palety do zwolnienia.")

        released = LabQualityRepository.release_pallet_from_lab(
            pallet_code=pallet_code,
            pallet_type=pallet_type,
            linia=linia,
            user_login=user_login,
            comment=comment or "Zwolniono po badaniach laboratoryjnych (LAB)"
        )

        if not released:
            return ServiceResult.fail(f"Nie znaleziono aktywnej Blokady LAB dla palety {pallet_code}.")

        return ServiceResult.ok(
            data={"pallet_code": pallet_code, "status": "ZWOLNIONY_LAB"},
            message=f"Paleta {pallet_code} została pomyślnie zwolniona z Blokady LAB."
        )

    @staticmethod
    def check_pallet_lab_status(pallet_code: str) -> Dict[str, Any]:
        """
        Checks whether a pallet is safe to use or blocked by LAB.
        """
        blocked_info = LabQualityRepository.is_pallet_blocked(pallet_code)
        if blocked_info:
            return {
                "is_blocked": True,
                "status": "BLOKADA_LAB",
                "reason": blocked_info.get('powod_blokady'),
                "blocked_by": blocked_info.get('zablokowal_login'),
                "blocked_at": str(blocked_info.get('data_blokady')),
                "message": f"ODRZUCONO: Paleta {pallet_code} posiada aktywną Blokadę LAB ({blocked_info.get('powod_blokady')})."
            }
        return {
            "is_blocked": False,
            "status": "DOSTEPNY",
            "message": "Paleta nie posiada blokad jakościowych."
        }

    @staticmethod
    def get_all_active_blocks(linia: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch list of all currently active lab holds."""
        return LabQualityRepository.get_active_lab_blocks(linia)
