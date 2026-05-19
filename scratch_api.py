import requests

def test():
    resp = requests.post("http://127.0.0.1:8082/magazyn/inwentaryzacja/api/szukaj-regalu", json={"prefix": "R01", "sesja_id": 15})
    data = resp.json()
    print("KEYS:", list(data.get("rack_data", {}).keys()))
    print("R010102:", data.get("rack_data", {}).get("R010102"))

if __name__ == '__main__':
    test()
