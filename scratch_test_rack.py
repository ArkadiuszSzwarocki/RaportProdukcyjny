from app.services.inwentaryzacja_service import InwentaryzacjaService

def test():
    data = InwentaryzacjaService.get_rack_data('R01', 15)
    print("R01 Rack Data:", list(data.keys()))

if __name__ == '__main__':
    test()
