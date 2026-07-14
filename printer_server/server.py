import os
import json
import socket
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify
try:
    from flask_cors import CORS
except ModuleNotFoundError:
    CORS = None

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('PrinterServer')

app = Flask(__name__)

# Pełna konfiguracja CORS - niezbędne dla żądań z sieci prywatnej (Private-Network)
if CORS is not None:
    CORS(app, resources={r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "expose_headers": ["Access-Control-Allow-Private-Network"]
    }})
else:
    logger.warning("flask-cors is not installed; using fallback CORS headers.")

@app.after_request
def after_request(response):
    response.headers.setdefault('Access-Control-Allow-Origin', '*')
    response.headers.setdefault('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.setdefault('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
    response.headers.add('Access-Control-Allow-Private-Network', 'true')
    return response

# Stała mapa IP jako fallback / wartości domyślne (skopiowana z Node.js)
PRINTER_IP_MAP = {
    'Biuro': '192.168.1.236',
    'Magazyn': '192.168.1.237',
    'Handel': '192.168.1.240',
    'OSIP': '192.168.1.160',
}

def _read_float_env(name, default_value, minimum=None):
    raw_value = os.getenv(name)
    if raw_value is None:
        value = float(default_value)
    else:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = float(default_value)
    if minimum is not None:
        value = max(float(minimum), value)
    return value


def _read_int_env(name, default_value, minimum=None, maximum=None):
    raw_value = os.getenv(name)
    if raw_value is None:
        value = int(default_value)
    else:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = int(default_value)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


DEFAULT_PRINTER_TCP_TIMEOUT = _read_float_env('PRINTER_TCP_TIMEOUT', 5.0, minimum=0.5)
DEFAULT_PRINTER_TCP_RETRIES = _read_int_env('PRINTER_TCP_RETRIES', 3, minimum=1, maximum=5)
DEFAULT_PRINTER_TCP_RETRY_DELAY = _read_float_env('PRINTER_TCP_RETRY_DELAY', 0.6, minimum=0.0)


def wyslij_do_drukarki(zpl, ip, port=9100, timeout=None, retries=None, retry_delay=None):
    """Wysyła surowy ciąg ZPL na podany adres IP i port drukarki za pomocą gniazda TCP."""
    tcp_timeout = DEFAULT_PRINTER_TCP_TIMEOUT if timeout is None else max(0.5, float(timeout))
    attempts = DEFAULT_PRINTER_TCP_RETRIES if retries is None else max(1, int(retries))
    pause_s = DEFAULT_PRINTER_TCP_RETRY_DELAY if retry_delay is None else max(0.0, float(retry_delay))

    last_error_message = 'Błąd połączenia z drukarką'

    for attempt in range(1, attempts + 1):
        try:
            logger.info(f"[TCP] Wysyłanie danych do {ip}:{port} (próba {attempt}/{attempts})...")
            with socket.create_connection((ip, port), timeout=tcp_timeout) as tcp_socket:
                tcp_socket.sendall(zpl.encode('utf-8'))

            if attempt > 1:
                logger.info(f"[TCP] Sukces po ponowieniu dla {ip}:{port} (próba {attempt}/{attempts})")
            return True
        except socket.timeout:
            last_error_message = 'Timeout połączenia z drukarką'
            logger.warning(f"[TCP] Timeout dla {ip}:{port} (próba {attempt}/{attempts})")
        except Exception as e:
            last_error_message = f'Błąd połączenia: {str(e)}'
            logger.warning(f"[TCP] Błąd połączenia z {ip}:{port} (próba {attempt}/{attempts}) - {str(e)}")

        if attempt < attempts and pause_s > 0:
            time.sleep(pause_s)

    logger.error(f"[TCP] Błąd końcowy dla {ip}:{port} po {attempts} próbach: {last_error_message}")
    raise Exception(f'{last_error_message} (po {attempts} próbach)')

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"success": True, "message": "Serwer druku (Python) działa poprawnie."})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    import signal
    logger.info("Otrzymano polecenie wyłączenia serwera druku.")
    try:
        os.kill(os.getpid(), signal.SIGINT)
    except Exception as e:
        logger.error(f"Błąd podczas wyłączania: {e}")
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            import sys
            sys.exit(0)
    return jsonify({"success": True, "message": "Serwer druku wyłączany."})

@app.route('/printers', methods=['GET'])
def printers():
    items = []
    for name, ip in PRINTER_IP_MAP.items():
        if not ip:
            continue
        items.append(
            {
                'name': str(name),
                'ip': str(ip),
                'lokalizacja': 'Sieć',
            }
        )
    return jsonify({'success': True, 'printers': items})

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
        
        id_palety = p.get('nrPalety') or p.get('nr_palety') or p.get('displayId') or p.get('id') or 'Brak ID'
        nazwa = p.get('nazwa') or p.get('product_name') or p.get('productName') or 'Brak Nazwy'
        partia = p.get('batchNumber') or p.get('nr_partii') or p.get('batchId') or '---'
        uwagi = p.get('labAnalysisNotes') or p.get('labNotes') or ''
        
        d_prod_raw = p.get('dataProdukcji') or p.get('data_produkcji') or p.get('productionDate') or '---'
        d_prod = d_prod_raw.split('T')[0] if 'T' in d_prod_raw else d_prod_raw
        
        d_wazn_raw = p.get('dataPrzydatnosci') or p.get('data_przydatnosci') or p.get('expiryDate') or '---'
        d_wazn = d_wazn_raw.split('T')[0] if 'T' in d_wazn_raw else d_wazn_raw

        waga_value = p.get('currentWeight') or p.get('qty') or p.get('quantityKg') or p.get('producedWeight') or p.get('waga') or 0
        try:
            waga = f"{float(waga_value):.0f}"
        except:
            waga = str(waga_value)
            
        unit_raw = p.get('unit') or p.get('jednostka') or 'kg'
        if unit_raw.lower() in ['szt.', 'szt', 'pcs']:
            naglowek_wagi = "ILOSC:"
            waga_text = f"{waga} szt."
        else:
            naglowek_wagi = "WAGA NETTO:"
            waga_text = f"{waga} kg"

        logger.info(f"- Etykieta: paleta={id_palety}, produkcja={d_prod}, waznosc={d_wazn}, ilosc/waga={waga_text}")

        typ_str = str(typ).lower() if typ else str(p.get('p_type', '')).lower()
        if 'packaging' in typ_str or 'opakowanie' in typ_str:
            tytul = 'OPAKOWANIE'
        elif 'raw' in typ_str or 'surowiec' in typ_str:
            tytul = 'SUROWIEC'
        else:
            tytul = 'WYRÓB GOTOWY'
        
        # Konstrukcja ZPL dopasowana do etykiety 4x6 cala (101.6mm x 150mm)
        # Przy 203 DPI to ok. 800 x 1200 punktów
        zpl_string = "^XA^CI28\n"
        zpl_string += "^PW800\n"       # Szerokość (z marginesem)
        zpl_string += "^LL1200\n"      # Długość (standard 150mm)
        zpl_string += "^MNG\n"         # Media Tracking: GAP (szczelina)
        zpl_string += "^PON\n"         # Orientacja: Normal
        
        # Ramka zewnętrzna (nieco szersza, by lepiej wykorzystać 4 cale)
        zpl_string += "^FO10,10^GB780,1180,4^FS\n"
        
        # Nagłówek (Surowiec / Wyrób Gotowy / Opakowanie)
        zpl_string += f"^FO40,50^A0N,40,40^FD{tytul}^FS\n"
        
        # Nazwa Produktu
        zpl_string += f"^FO40,110^A0N,60,60^FB720,2,0,L^FD{str(nazwa)[:60]}^FS\n"
        
        # Kod QR (Wyśrodkowany, współczynnik powiększenia 12)
        zpl_string += f"^FO250,190^BQN,2,12^FDQA,{id_palety}^FS\n"
        
        # Tekst ID palety pod kodem QR (wyśrodkowany bold)
        zpl_string += f"^FO40,510^A0N,35,35^FB720,1,0,C^FD{id_palety}^FS\n"
        
        # Dane produkcyjne
        zpl_string += f"^FO60,560^A0N,35,35^FDPARTIA: {partia}^FS\n"
        zpl_string += f"^FO60,610^A0N,35,35^FDPRODUKCJA: {d_prod}^FS\n"
        if tytul != 'WYRÓB GOTOWY':
            zpl_string += f"^FO60,660^A0N,35,35^FDWAZNOSC:   {d_wazn}^FS\n"
            
        # Waga (w 2 liniach: naglowek + wartosc)
        zpl_string += f"^FO60,950^A0N,72,72^FD{naglowek_wagi}^FS\n"
        zpl_string += f"^FO60,1030^A0N,100,100^FD{waga_text}^FS\n"
        zpl_string += "^XZ"

    try:
        wyslij_do_drukarki(zpl_string, target_ip)
        logger.info("✅ Sukces: Etykieta wysłana do drukarki.")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ Błąd wydruku: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/drukuj-pdf', methods=['POST'])
def drukuj_pdf():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Brak pliku PDF"}), 400
        
    file = request.files['file']
    drukarka = request.form.get('drukarka')
    ip = request.form.get('ip')
    
    target_printer = ip or drukarka
    if not target_printer:
        try:
            import win32print
            target_printer = win32print.GetDefaultPrinter()
        except ImportError:
            target_printer = "Nieznana Drukarka"

    import tempfile
    fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="drukowanie_")
    os.close(fd)
    file.save(pdf_path)

    logger.info(f"Odebrano PDF do druku. Drukarka: {target_printer}")

    success = False
    error_msg = ""
    try:
        import win32api
        import win32print
        import win32ui
        import fitz
        from PIL import Image, ImageWin
        
        doc = fitz.open(pdf_path)
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(target_printer)
        
        printable_width = hDC.GetDeviceCaps(8)
        printable_height = hDC.GetDeviceCaps(10)
        
        hDC.StartDoc("Raport Produkcyjny")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            if img.size[0] > img.size[1]:
                img = img.rotate(90, expand=True)
                
            ratios = [1.0 * printable_width / img.size[0], 1.0 * printable_height / img.size[1]]
            scale = min(ratios)
            
            hDC.StartPage()
            dib = ImageWin.Dib(img)
            scaled_width, scaled_height = [int(scale * i) for i in img.size]
            
            x1 = int((printable_width - scaled_width) / 2)
            y1 = int((printable_height - scaled_height) / 2)
            x2 = x1 + scaled_width
            y2 = y1 + scaled_height
            
            dib.draw(hDC.GetHandleOutput(), (x1, y1, x2, y2))
            hDC.EndPage()
            
        hDC.EndDoc()
        hDC.DeleteDC()
        doc.close()
        logger.info("✅ Wydrukowano PDF pomyślnie.")
        success = True
    except Exception as e:
        logger.error(f"❌ PyMuPDF print failed: {e}. Próba ShellExecute...")
        try:
            import win32api
            win32api.ShellExecute(0, "printto", pdf_path, f'"{target_printer}"', ".", 0)
            time.sleep(5)
            logger.info("✅ Wydrukowano PDF pomyślnie przez ShellExecute.")
            success = True
        except Exception as ex:
            error_msg = str(ex)
            logger.error(f"❌ ShellExecute print failed: {ex}")
    finally:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": f"Błąd druku PDF: {error_msg}"}), 500

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
        protocol = "HTTPS"
    else:
        logger.info("⚠️ SSL: Brak lokalnych certyfikatów. Uruchamiam w trybie HTTP.")
        protocol = "HTTP"
        
    logger.info(f"\n🚀 MOST DO DRUKAREK AKTYWNY (Python) na porcie {port} ({protocol})")
    app.run(host='0.0.0.0', port=port, ssl_context=ssl_context)
