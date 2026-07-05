from app.repositories.agro_opakowania_repository import AgroOpakowaniaRepository

class AgroOpakowaniaService:
    @staticmethod
    def get_packaging_inventory(linia='Agro'):
        return AgroOpakowaniaRepository.get_packaging_inventory(linia=linia)

    @staticmethod
    def create_packaging(nazwa, ilosc, lokalizacja=None, linia='Agro'):
        return AgroOpakowaniaRepository.create_packaging(nazwa=nazwa, ilosc=ilosc, lokalizacja=lokalizacja, linia=linia)

    @staticmethod
    def edit_packaging(record_id, nazwa=None, ilosc=None, lokalizacja=None, linia='Agro'):
        return AgroOpakowaniaRepository.edit_packaging(record_id=record_id, nazwa=nazwa, ilosc=ilosc, lokalizacja=lokalizacja, linia=linia)

    @staticmethod
    def delete_packaging(record_id, linia='Agro'):
        return AgroOpakowaniaRepository.delete_packaging(record_id=record_id, linia=linia)

    @staticmethod
    def adjust_packaging_inventory(record_id, actual_qty, worker_login=None, linia='Agro'):
        return AgroOpakowaniaRepository.adjust_packaging_inventory(record_id=record_id, actual_qty=actual_qty, worker_login=worker_login, linia=linia)

