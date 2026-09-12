"""Warehouse Pallet Service Facade.

Maintains 100% backward compatibility with existing callers while delegating
to specialized domain command services under `app.services.pallets`.
"""

from app.services.pallets.pallet_creation_service import PalletCreationService
from app.services.pallets.pallet_confirmation_service import PalletConfirmationService
from app.services.pallets.pallet_management_service import PalletManagementService


class WarehousePalletService:
    """Facade for warehouse pallet operations."""

    @staticmethod
    def dodaj_palete(plan_id, linia, waga_palety, nr_plomby, data_produkcji, printer_ip, printer_name, user_login, app_obj, is_ajax, safe_return_url):
        """Add paleta to buffer via PalletCreationService."""
        return PalletCreationService.dodaj_palete(
            plan_id=plan_id,
            linia=linia,
            waga_palety=waga_palety,
            nr_plomby=nr_plomby,
            data_produkcji=data_produkcji,
            printer_ip=printer_ip,
            printer_name=printer_name,
            user_login=user_login,
            app_obj=app_obj,
            is_ajax=is_ajax,
            safe_return_url=safe_return_url,
        )

    @staticmethod
    def potwierdz_palete(paleta_id, linia, user_login, app_obj, update_paleta_workowanie, update_paleta_magazyn, is_ajax, safe_return_url):
        """Confirm paleta acceptance via PalletConfirmationService."""
        return PalletConfirmationService.potwierdz_palete(
            paleta_id=paleta_id,
            linia=linia,
            user_login=user_login,
            app_obj=app_obj,
            update_paleta_workowanie=update_paleta_workowanie,
            update_paleta_magazyn=update_paleta_magazyn,
            is_ajax=is_ajax,
            safe_return_url=safe_return_url,
        )

    @staticmethod
    def usun_palete(id, linia, user_login, is_ajax, safe_return_url, conn=None):
        """Delete paleta from buffer via PalletManagementService."""
        return PalletManagementService.usun_palete(
            id=id,
            linia=linia,
            user_login=user_login,
            is_ajax=is_ajax,
            safe_return_url=safe_return_url,
            conn=conn,
        )

    @staticmethod
    def edytuj_palete(paleta_id, linia, waga_palety, user_login, update_paleta_workowanie, is_ajax, safe_return_url):
        """Edit paleta weight in buffer via PalletManagementService."""
        return PalletManagementService.edytuj_palete(
            paleta_id=paleta_id,
            linia=linia,
            waga_palety=waga_palety,
            user_login=user_login,
            update_paleta_workowanie=update_paleta_workowanie,
            is_ajax=is_ajax,
            safe_return_url=safe_return_url,
        )
