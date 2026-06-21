import requests

session = requests.Session()
login_data = {
    'login': 'MasterAdmin',
    'haslo': 'MasterAdmin123!'
}
session.post('http://localhost:8082/login', data=login_data)
response = session.get('http://localhost:8082/?sekcja=Workowanie&linia=AGRO')

with open('scratch/rendered.html', 'w', encoding='utf-8') as f:
    f.write(response.text)

print("Saved to scratch/rendered.html")
