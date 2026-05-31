"""
PrintServer — serwer drukowania etykiet ZPL na drukarce Zebra.

Tryby pracy:
  A) bezpośredni TCP (Zebra osiągalna przez sieć — ZPL przez socket na port 9100)
  B) Windows Spooler (drukarka zainstalowana jako drukarka Windows — win32print)

Konfiguracja (w .env lub app config):
  PRINTER_MODE = tcp | windows
  PRINTER_IP   = 192.168.1.100          (dla trybu tcp)
  PRINTER_PORT = 9100
  PRINTER_NAME = ZebraLP2824            (dla trybu windows)
"""

import requests
import urllib3
import os
from datetime import datetime

# Wyłączenie ostrzeżeń o certyfikatach self-signed (most działa na https adhoc)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PrintServer:
    def __init__(self):
        # Mostek (bridge) działa zazwyczaj na tej samej maszynie co serwer WWW
        self.bridge_url = os.getenv('PRINTER_BRIDGE_URL', 'https://127.0.0.1:3001')
        self.bridge_connect_timeout = float(os.getenv('PRINTER_BRIDGE_CONNECT_TIMEOUT', '2'))
        self.bridge_read_timeout = float(os.getenv('PRINTER_BRIDGE_READ_TIMEOUT', '12'))
        self.printer_ip = os.getenv('PRINTER_IP', '192.168.1.237')
        self.printer_name = "Magazyn"

    def test_connection(self) -> tuple[bool, str]:
        """Sprawdza połączenie z mostkiem druku."""
        try:
            # Sprawdzamy czy sam mostek żyje
            resp = requests.get(f"{self.bridge_url}/status", verify=False, timeout=2)
            if resp.status_code == 200:
                return True, f"Mostek druku aktywny ({self.bridge_url})"
            return False, f"Mostek zwrócił status {resp.status_code}"
        except Exception as e:
            return False, f"Błąd połączenia z mostkiem: {str(e)}"

    def list_network_printers(self) -> list[dict]:
        """Pobiera listę drukarek widocznych dla mostka druku (sieć LAN)."""
        try:
            resp = requests.get(
                f"{self.bridge_url}/printers",
                verify=False,
                timeout=(self.bridge_connect_timeout, min(self.bridge_read_timeout, 8)),
            )
            if resp.status_code != 200:
                return []

            body = resp.json() if resp.content else {}
            raw_items = body.get('printers') if isinstance(body, dict) else []
            if not isinstance(raw_items, list):
                return []

            printers = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                ip = str(item.get('ip') or '').strip()
                if not ip:
                    continue
                printers.append(
                    {
                        'name': str(item.get('name') or item.get('nazwa') or f'Drukarka {ip}').strip(),
                        'ip': ip,
                        'lokalizacja': str(item.get('lokalizacja') or 'Sieć').strip(),
                    }
                )
            return printers
        except Exception:
            return []

    def print_pallet_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        """Wysyła dane palety do mostka z bezpośrednio wygenerowanym kodem ZPL 4x6."""
        nr_palety = str(label_data.get('nr_palety') or label_data.get('nrPalety') or '').strip()
        if not nr_palety:
            from app.utils.pallet_id import generate_pallet_id
            nr_palety = generate_pallet_id('AGRO', type='surowiec', record_id=label_data.get('id'))

        product_name = str(label_data.get('nazwa') or 'Brak nazwy').strip()
        nr_partii = str(label_data.get('partia') or '---').strip()
        data_produkcji = str(label_data.get('data') or datetime.now().strftime('%Y-%m-%d')).strip()
        data_przydatnosci = str(label_data.get('termin') or '---').strip()
        
        ilosc_val = label_data.get('ilosc')
        if ilosc_val is not None:
            qty_display = str(ilosc_val).replace('.0', '')
        else:
            qty_display = '0'

        linia = str(label_data.get('linia') or '').strip()

        zpl_string=f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FDSUROWIEC - {linia}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,340^BQN,2,10^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDPARTIA: {nr_partii}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
^FO40,950^A0N,50,50^FDTERMIN: {data_przydatnosci}^FS
^FO40,1050^A0N,60,60^FDWAGA NETTO:^FS
^FO350,1040^A0N,80,80^FD{qty_display} kg^FS
^XZ"""

        payload = {
            "drukarka": override_name or self.printer_name,
            "ip": override_ip or self.printer_ip,
            "dane": zpl_string
        }
        return self._send_to_bridge(payload)

    def print_finished_product_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        """Wysyła dane palety wyrobu gotowego do mostka ZPL 4x6 z bezp. wygenerowanym kodem ZPL."""
        nr_palety = str(label_data.get('nrPalety') or label_data.get('nr_palety') or '').strip()
        
        product_name = str(label_data.get('nazwa') or 'Brak nazwy').strip()
        data_produkcji = str(label_data.get('data') or datetime.now().strftime('%Y-%m-%d')).strip()
        
        ilosc_val = label_data.get('ilosc')
        if ilosc_val is not None:
            qty_display = str(ilosc_val).replace('.0', '')
        else:
            qty_display = '0'
            
        nr_palety_lp = label_data.get('nr_palety_lp') or ''
        linia = str(label_data.get('linia') or '').strip()

        zpl_string=f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FDWYROB GOTOWY - {linia}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,340^BQN,2,10^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDNR PALETY: {nr_palety_lp}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
^FO40,1000^A0N,70,70^FDWAGA NETTO:^FS
^FO40,1100^A0N,100,100^FD{qty_display} kg^FS
^XZ"""

        payload = {
            "drukarka": override_name or self.printer_name,
            "ip": override_ip or self.printer_ip,
            "dane": zpl_string
        }
        return self._send_to_bridge(payload)

    def print_location_label(self, label_data: dict) -> tuple[bool, str]:
        """Dla lokalizacji możemy wysłać surowy ZPL (mostek to wspiera)."""
        # Tu możemy zostawić stary ZPL lub przygotować dedykowany dla regałów
        zpl = f"^XA^CI28^PW812^LL1214^FO20,20^GB772,1174,4^FS"
        zpl += f"^FO60,100^A0N,100,100^FDREGAŁ: {label_data.get('lokalizacja')}^FS"
        zpl += f"^FO60,250^BY4^BQN,2,10^FDMA,{label_data.get('lokalizacja')}^FS"
        zpl += "^XZ"
        
        payload = {
            "drukarka": self.printer_name,
            "ip": self.printer_ip,
            "dane": zpl
        }
        return self._send_to_bridge(payload)

    def _send_to_bridge(self, payload: dict) -> tuple[bool, str]:
        target_name = payload.get('drukarka') or self.printer_name
        target_ip = payload.get('ip') or self.printer_ip
        target_hint = f"drukarka={target_name}, ip={target_ip}"
        try:
            resp = requests.post(
                f"{self.bridge_url}/drukuj-zpl",
                json=payload,
                verify=False,
                timeout=(self.bridge_connect_timeout, self.bridge_read_timeout),
            )
            try:
                body = resp.json()
            except ValueError:
                body = {}

            if resp.status_code == 200 and body.get('success'):
                return True, "Wysłano do drukarki przez mostek"

            bridge_msg = body.get('message') or f'Błąd mostka (HTTP {resp.status_code})'
            return False, f"{bridge_msg} ({target_hint})"
        except Exception as e:
            return False, f"Błąd komunikacji z mostkiem: {str(e)} ({target_hint})"

# Singleton
_printer = None

def get_printer() -> PrintServer:
    global _printer
    if _printer is None:
        _printer = PrintServer()
    return _printer
