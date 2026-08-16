from app.repositories.agro_opakowaniaplan_repository import AgroOpakowaniaPlanRepository

class AgroOpakowaniaPlanService:
    @staticmethod
    def get_linked_packaging(plan_id):
        return AgroOpakowaniaPlanRepository.get_linked_packaging(plan_id=plan_id)

    @staticmethod
    def get_all_linked_packaging(plan_id):
        return AgroOpakowaniaPlanRepository.get_all_linked_packaging(plan_id=plan_id)

    @staticmethod
    def _link_to_active_plan(cursor, opakowanie_id, lokalizacja, linia='Agro'):
        return AgroOpakowaniaPlanRepository._link_to_active_plan(cursor=cursor, opakowanie_id=opakowanie_id, lokalizacja=lokalizacja, linia=linia)

    @staticmethod
    def link_packaging_to_plan(opakowanie_id, plan_id, ilosc_pobrana=None, user_login=None):
        return AgroOpakowaniaPlanRepository.link_packaging_to_plan(opakowanie_id=opakowanie_id, plan_id=plan_id, ilosc_pobrana=ilosc_pobrana, user_login=user_login)

    @staticmethod
    def undo_packaging_link(link_id):
        return AgroOpakowaniaPlanRepository.undo_packaging_link(link_id=link_id)

    @staticmethod
    def finalize_packaging_usage(plan_id, szt_na_palecie, packaging_results, user_login):
        return AgroOpakowaniaPlanRepository.finalize_packaging_usage(plan_id=plan_id, szt_na_palecie=szt_na_palecie, packaging_results=packaging_results, user_login=user_login)

    @staticmethod
    def return_packaging_from_machine(opakowanie_id, stan_po, lokalizacja, user_login, is_partial=False, print_label=False):
        return AgroOpakowaniaPlanRepository.return_packaging_from_machine(opakowanie_id=opakowanie_id, stan_po=stan_po, lokalizacja=lokalizacja, user_login=user_login, is_partial=is_partial, print_label=print_label)

    @staticmethod
    def undo_packaging_return(link_id, user_login):
        return AgroOpakowaniaPlanRepository.undo_packaging_return(link_id=link_id, user_login=user_login)

    @staticmethod
    def build_packaging_return_label_zpl(label_data):
        return AgroOpakowaniaPlanRepository.build_packaging_return_label_zpl(label_data=label_data)

    @staticmethod
    def print_packaging_return_label(label_data):
        return AgroOpakowaniaPlanRepository.print_packaging_return_label(label_data=label_data)

