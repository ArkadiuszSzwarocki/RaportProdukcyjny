from app.repositories.agro_surowce_repository import AgroSurowceRepository

class AgroSurowceService:
    @staticmethod
    def get_inventory(linia='Agro'):
        return AgroSurowceRepository.get_inventory(linia=linia)

    @staticmethod
    def get_inventory_grouped(linia='Agro', pkg_form=None):
        return AgroSurowceRepository.get_inventory_grouped(linia=linia, pkg_form=pkg_form)

    @staticmethod
    def get_inventory_by_location(linia='Agro'):
        return AgroSurowceRepository.get_inventory_by_location(linia=linia)

    @staticmethod
    def get_history(limit=100, status=None, linia='Agro', data=None, plan_id=None):
        return AgroSurowceRepository.get_history(limit=limit, status=status, linia=linia, data=data, plan_id=plan_id)

    @staticmethod
    def get_dictionary():
        return AgroSurowceRepository.get_dictionary()

    @staticmethod
    def get_occupied_locations(linia='Agro'):
        return AgroSurowceRepository.get_occupied_locations(linia=linia)

    @staticmethod
    def get_suggested_location(nazwa, linia='Agro'):
        return AgroSurowceRepository.get_suggested_location(nazwa=nazwa, linia=linia)

    @staticmethod
    def add_delivery(nazwa, ilosc, author_login, linia='Agro', komentarz=None, nr_partii=None, data_produkcji=None, data_przydatnosci=None, pkg_form='bags'):
        return AgroSurowceRepository.add_delivery(nazwa=nazwa, ilosc=ilosc, author_login=author_login, linia=linia, komentarz=komentarz, nr_partii=nr_partii, data_produkcji=data_produkcji, data_przydatnosci=data_przydatnosci, pkg_form=pkg_form)

    @staticmethod
    def edit_delivery(ruch_id, nazwa=None, ilosc=None, komentarz=None):
        return AgroSurowceRepository.edit_delivery(ruch_id=ruch_id, nazwa=nazwa, ilosc=ilosc, komentarz=komentarz)

    @staticmethod
    def delete_delivery(ruch_id):
        return AgroSurowceRepository.delete_delivery(ruch_id=ruch_id)

    @staticmethod
    def confirm_delivery(ruch_id, worker_login, linia='Agro', lokalizacja=None, nr_partii=None, data_produkcji=None, data_przydatnosci=None):
        return AgroSurowceRepository.confirm_delivery(ruch_id=ruch_id, worker_login=worker_login, linia=linia, lokalizacja=lokalizacja, nr_partii=nr_partii, data_produkcji=data_produkcji, data_przydatnosci=data_przydatnosci)

    @staticmethod
    def use_for_production(surowiec_id, ilosc, worker_login, plan_id=None, linia='Agro', komentarz=None, zbiornik=None):
        return AgroSurowceRepository.use_for_production(surowiec_id=surowiec_id, ilosc=ilosc, worker_login=worker_login, plan_id=plan_id, linia=linia, komentarz=komentarz, zbiornik=zbiornik)

    @staticmethod
    def issue_external(surowiec_id, ilosc, worker_login, linia='Agro', komentarz=None):
        return AgroSurowceRepository.issue_external(surowiec_id=surowiec_id, ilosc=ilosc, worker_login=worker_login, linia=linia, komentarz=komentarz)

    @staticmethod
    def confirm_external_issue(ruch_id, worker_login, linia='Agro'):
        return AgroSurowceRepository.confirm_external_issue(ruch_id=ruch_id, worker_login=worker_login, linia=linia)

    @staticmethod
    def adjust_inventory(surowiec_id, actual_qty, worker_login, linia='Agro', komentarz=None):
        return AgroSurowceRepository.adjust_inventory(surowiec_id=surowiec_id, actual_qty=actual_qty, worker_login=worker_login, linia=linia, komentarz=komentarz)

    @staticmethod
    def issue_warehouse(surowiec_id, ilosc, worker_login, linia='Agro', komentarz=None):
        return AgroSurowceRepository.issue_warehouse(surowiec_id=surowiec_id, ilosc=ilosc, worker_login=worker_login, linia=linia, komentarz=komentarz)

    @staticmethod
    def get_warehouse_entries(limit=1000, linia='Agro', date_from=None, date_to=None):
        return AgroSurowceRepository.get_warehouse_entries(limit=limit, linia=linia, date_from=date_from, date_to=date_to)

    @staticmethod
    def get_combined_report(limit=2000, linia='Agro', date_from=None, date_to=None):
        return AgroSurowceRepository.get_combined_report(limit=limit, linia=linia, date_from=date_from, date_to=date_to)

