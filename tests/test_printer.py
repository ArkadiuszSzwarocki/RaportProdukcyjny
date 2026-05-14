import mysql.connector
import os
import sys
import requests
import json
import urllib3
sys.path.append(os.getcwd())
from app.config import DB_CONFIG

# Wyłączamy ostrzeżenia o niezaufanym certyfikacie SSL (adhoc SSL)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_print():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    # Pobierz jedną testową paletę wyrobu gotowego
    cursor.execute("SELECT * FROM magazyn_palety LIMIT 1")
    paleta = cursor.fetchone()
    conn.close()

    if not paleta:
        print("Nie znaleziono zadnych palet w bazie.")
        return

    print(f"Pobrano palete do testu: {paleta['produkt']} (ID: {paleta['nr_palety'] or paleta['id']})")

    # Formatujemy payload
    payload = {
        "drukarka": "Magazyn",
        "ip": "192.168.1.237",
        "typ": "wyrób gotowy",
        "dane": {
            "palletData": {
                "nrPalety": paleta['nr_palety'] or paleta['id'],
                "productName": paleta['produkt'],
                "batchNumber": paleta['nr_partii'] or 'TEST-123',
                "productionDate": str(paleta['data_produkcji']) if paleta['data_produkcji'] else '2026-05-12',
                "expiryDate": str(paleta['data_przydatnosci']) if paleta['data_przydatnosci'] else '2026-11-12',
                "currentWeight": paleta['waga_netto'],
                "labNotes": "Wydruk testowy z Pythona"
            }
        }
    }

    url = "https://127.0.0.1:3001/drukuj-zpl"
    print(f"Wysylam zadanie druku na adres {url}...")
    
    try:
        response = requests.post(url, json=payload, verify=False, timeout=10)
        if response.status_code == 200:
            print("SUKCES! Serwer przyjal zadanie i etykieta zostala wyslana do drukarki.")
        else:
            print(f"BLAD SERWERA: {response.status_code} - {response.text}")
    except requests.exceptions.ConnectionError as ce:
        print(f"BLAD POLACZENIA: {str(ce)}")
    except Exception as e:
        print(f"WYJATEK: {str(e)}")

if __name__ == "__main__":
    test_print()
