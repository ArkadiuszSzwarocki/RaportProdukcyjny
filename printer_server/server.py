import os
import json
import socket
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('PrinterServer')

app = Flask(__name__)

# Pełna konfiguracja CORS - niezbędne dla żądań z sieci prywatnej (Private-Network)
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
    "expose_headers": ["Access-Control-Allow-Private-Network"]
}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Private-Network', 'true')
    return response

# Stała mapa IP jako fallback / wartości domyślne (skopiowana z Node.js)
PRINTER_IP_MAP = {
    'Biuro': '192.168.1.236',
    'Magazyn': '192.168.1.237',
    'Handel': '192.168.1.240',
    'OSIP': '192.168.1.160',
}

def wyslij_do_drukarki(zpl, ip, port=9100, timeout=5.0):
    """Wysyła surowy ciąg ZPL na podany adres IP i port drukarki za pomocą gniazda TCP."""
    try:
        logger.info(f"[TCP] Wysyłanie danych do {ip}:{port}...")
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.sendall(zpl.encode('utf-8'))
        return True
    except socket.timeout:
        logger.error(f"[TCP] Błąd: Timeout połączenia z drukarką {ip}:{port}")
        raise Exception('Timeout połączenia z drukarką')
    except Exception as e:
        logger.error(f"[TCP] Błąd: Nie udało się połączyć z {ip}:{port} - {str(e)}")
        raise Exception(f'Błąd połączenia: {str(e)}')

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"success": True, "message": "Serwer druku (Python) działa poprawnie."})

@app.route('/drukuj-zpl', methods=['POST'])
def drukuj_zpl():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "Brak danych (wymagany JSON)."}), 400

    dane = data.get('dane')
    drukarka = data.get('drukarka')
    ip = data.get('ip')
    typ = data.get('typ', 'brak_typu')

    # Ustalanie docelowego IP: priorytet ma pole 'ip', potem mapa nazw
    target_ip = ip or PRINTER_IP_MAP.get(drukarka)

    logger.info(f"\n--- NOWE ZLECENIE ---")
    logger.info(f"- Typ: {typ}")
    logger.info(f"- Drukarka (nazwa): {drukarka or 'dynamiczna'}")
    logger.info(f"- IP: {target_ip}")

    if not target_ip:
        logger.error("❌ BŁĄD: Nie określono adresu IP drukarki.")
        return jsonify({"success": False, "message": "Nieznana drukarka lub brak adresu IP."}), 400

    zpl_string = ""

    if isinstance(dane, str):
        zpl_string = dane
    else:
        # Generowanie ZPL z obiektu JSON (identycznie jak w Mlecznej Drodze)
        p = dane.get('palletData') if isinstance(dane, dict) and 'palletData' in dane else dane
        
        id_palety = p.get('nrPalety') or p.get('displayId') or p.get('id') or 'Brak ID'
        nazwa = p.get('nazwa') or p.get('productName') or 'Brak Nazwy'
        partia = p.get('batchNumber') or p.get('batchId') or '---'
        uwagi = p.get('labAnalysisNotes') or p.get('labNotes') or ''
        
        d_prod_raw = p.get('dataProdukcji') or p.get('productionDate') or '---'
        d_prod = d_prod_raw.split('T')[0] if 'T' in d_prod_raw else d_prod_raw
        
        d_wazn_raw = p.get('dataPrzydatnosci') or p.get('expiryDate') or '---'
        d_wazn = d_wazn_raw.split('T')[0] if 'T' in d_wazn_raw else d_wazn_raw

        waga_value = p.get('currentWeight') or p.get('quantityKg') or p.get('producedWeight') or 0
        try:
            waga = f"{float(waga_value):.0f}"
        except:
            waga = str(waga_value)

        logger.info(f"- Etykieta: paleta={id_palety}, produkcja={d_prod}, waznosc={d_wazn}, waga={waga}kg")

        tytul = 'SUROWIEC' if 'raw' in str(typ).lower() else 'WYRÓB GOTOWY'
        
        # Konstrukcja ZPL dopasowana do etykiety 4x6 cala (101.6mm x 150mm)
        # Przy 203 DPI to ok. 800 x 1200 punktów
        zpl_string = "^XA^CI28\n"
        zpl_string += "^PW800\n"       # Szerokość (z marginesem)
        zpl_string += "^LL1200\n"      # Długość (standard 150mm)
        zpl_string += "^MNG\n"         # Media Tracking: GAP (szczelina)
        zpl_string += "^PON\n"         # Orientacja: Normal
        
        # Ramka zewnętrzna (nieco szersza, by lepiej wykorzystać 4 cale)
        zpl_string += "^FO10,10^GB780,1180,4^FS\n"
        
        # Nagłówek (Surowiec / Wyrób Gotowy)
        zpl_string += f"^FO40,50^A0N,40,40^FD{tytul}^FS\n"
        
        # Nazwa Produktu
        zpl_string += f"^FO40,110^A0N,60,60^FB720,2,0,L^FD{str(nazwa)[:60]}^FS\n"
        
        # Kod QR (Wyśrodkowany, współczynnik powiększenia 8)
        zpl_string += f"^FO300,250^BQN,2,8^FDQA,{id_palety}^FS\n"
        
        # Tekst ID palety pod kodem QR (wyśrodkowany bold)
        zpl_string += f"^FO40,465^A0N,35,35^FB720,1,0,C^FD{id_palety}^FS\n"
        
        # Dane produkcyjne
        zpl_string += f"^FO60,520^A0N,35,35^FDPARTIA: {partia}^FS\n"
        zpl_string += f"^FO60,570^A0N,35,35^FDPRODUKCJA: {d_prod}^FS\n"
        zpl_string += f"^FO60,620^A0N,35,35^FDWAZNOSC:   {d_wazn}^FS\n"
        
        if uwagi:
            uwagi_clean = str(uwagi).replace('\n', ' ')
            zpl_string += f"^FO60,680^A0N,30,30^FB700,6,0,L^FDNOTATKI LAB: {uwagi_clean}^FS\n"
            
        # Waga (w 2 liniach: naglowek + wartosc)
        zpl_string += "^FO60,970^A0N,72,72^FDWAGA NETTO:^FS\n"
        zpl_string += f"^FO60,1050^A0N,100,100^FD{waga} kg^FS\n"
        zpl_string += "^XZ"

    try:
        wyslij_do_drukarki(zpl_string, target_ip)
        logger.info("✅ Sukces: Etykieta wysłana do drukarki.")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ Błąd wydruku: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    port = 3001
    
    # Próba załadowania certyfikatów SSL
    # Zgodnie z oryginałem, serwer działa na HTTPS by przeglądarki na skanerach ufały połączeniu
    cert_file = './server.cert'
    key_file = './server.key'
    
    ssl_context = None
    if os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_context = (cert_file, key_file)
        logger.info("✅ SSL: Certyfikaty aktywne z plików lokalnych.")
    else:
        logger.info("⚠️ SSL: Brak lokalnych certyfikatów. Generuję certyfikaty 'adhoc' (wymaga pyOpenSSL).")
        ssl_context = 'adhoc'
        
    logger.info(f"\n🚀 MOST DO DRUKAREK AKTYWNY (Python) na porcie {port} (HTTPS)")
    app.run(host='0.0.0.0', port=port, ssl_context=ssl_context)
