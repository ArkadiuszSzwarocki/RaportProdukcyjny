import requests
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Test endpoint
url = "http://127.0.0.1:3001/drukuj-zpl"

# Testowy payload
payload = {
    "drukarka": "Zebra Produkcja",
    "ip": "192.168.1.160",
    "typ": "surowiec",
    "dane": """^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FDSUROWIEC - TEST^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FDTEST PRODUCT^FS
^FO250,340^BQN,2,10^FDQA,TEST123^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FDTEST123^FS
^FO40,750^A0N,50,50^FDPARTIA: 123^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: 2026-07-09^FS
^FO40,950^A0N,50,50^FDPRZYDATNOSC: 2027-07-09^FS
^FO40,1100^A0N,70,70^FDWAGA: 100 kg^FS
^XZ"""
}

print('=' * 70)
print('TEST ENDPOINTU /drukuj-zpl')
print('=' * 70)

print(f'\n📡 Wysyłam zapytanie do: {url}')
print(f'📦 Payload: drukarka={payload["drukarka"]}, ip={payload["ip"]}, typ={payload["typ"]}')

try:
    response = requests.post(
        url,
        json=payload,
        verify=False,
        timeout=5
    )
    
    print(f'\n📊 Status Code: {response.status_code}')
    print(f'📄 Headers: {dict(response.headers)}')
    
    try:
        json_response = response.json()
        print(f'\n✅ JSON Response:')
        print(json.dumps(json_response, indent=2, ensure_ascii=False))
    except Exception:
        print(f'\n📄 Text Response:')
        print(response.text)
        
except Exception as e:
    print(f'\n❌ Błąd: {e}')
    import traceback
    traceback.print_exc()
