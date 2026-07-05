from app.repositories.agro_tanks_repository import AgroTanksRepository

class AgroTanksService:
    @staticmethod
    def get_production_tanks():
        return AgroTanksRepository.get_production_tanks()

    @staticmethod
    def normalize_production_tank(tank_code):
        return AgroTanksRepository.normalize_production_tank(tank_code=tank_code)

    @staticmethod
    def get_production_moves(limit=100, linia='Agro'):
        return AgroTanksRepository.get_production_moves(limit=limit, linia=linia)

    @staticmethod
    def return_from_production(surowiec_id, ilosc, worker_login, plan_id=None, linia='Agro', komentarz=None, ruch_produkcja_id=None, lokalizacja=None):
        return AgroTanksRepository.return_from_production(surowiec_id=surowiec_id, ilosc=ilosc, worker_login=worker_login, plan_id=plan_id, linia=linia, komentarz=komentarz, ruch_produkcja_id=ruch_produkcja_id, lokalizacja=lokalizacja)

    @staticmethod
    def get_production_items_for_return(linia='Agro', limit=200):
        return AgroTanksRepository.get_production_items_for_return(linia=linia, limit=limit)

    @staticmethod
    def get_production_inventory(limit=500, linia='Agro'):
        return AgroTanksRepository.get_production_inventory(limit=limit, linia=linia)

    @staticmethod
    def get_production_inventory_snapshot(limit=4000, linia='Agro', show_empty=False):
        return AgroTanksRepository.get_production_inventory_snapshot(limit=limit, linia=linia, show_empty=show_empty)

    @staticmethod
    def get_production_tank_history(tank_code, limit=300, linia='Agro'):
        return AgroTanksRepository.get_production_tank_history(tank_code=tank_code, limit=limit, linia=linia)

    @staticmethod
    def adjust_production_inventory(ruch_id, actual_qty, worker_login, linia='Agro', komentarz=None):
        return AgroTanksRepository.adjust_production_inventory(ruch_id=ruch_id, actual_qty=actual_qty, worker_login=worker_login, linia=linia, komentarz=komentarz)

    @staticmethod
    def get_current_running_plan(linia='Agro'):
        return AgroTanksRepository.get_current_running_plan(linia=linia)

    @staticmethod
    def get_active_workowanie_plan(linia='Agro', target_date=None):
        return AgroTanksRepository.get_active_workowanie_plan(linia=linia, target_date=target_date)

    @staticmethod
    def get_finished_plans_of_day(linia='Agro', target_date=None):
        return AgroTanksRepository.get_finished_plans_of_day(linia=linia, target_date=target_date)

    @staticmethod
    def auto_register_pallet(plan_id, linia='AGRO', source_instance=None):
        return AgroTanksRepository.auto_register_pallet(plan_id=plan_id, linia=linia, source_instance=source_instance)

    @staticmethod
    def rename_pallet(surowiec_id, new_name, worker_login, linia='Agro'):
        return AgroTanksRepository.rename_pallet(surowiec_id=surowiec_id, new_name=new_name, worker_login=worker_login, linia=linia)


from app.repositories.agro_tanks_repository import _normalize_tank_code, _classify_tank_zone, _is_additive_material, _get_auto_pallet_cooldown_seconds, _select_preferred_printer, _sanitize_zpl_text, _format_quantity_label

