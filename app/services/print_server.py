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

    def print_pallet_label(self, label_data: dict) -> tuple[bool, str]:
        """Wysyła dane palety do mostka, który wygeneruje ZPL 4x6."""
        payload = {
            "drukarka": self.printer_name,
            "ip": self.printer_ip,
            "typ": "raw_material",
            "dane": {
                "palletData": {
                    "nrPalety": f"SUR-{label_data.get('id')}",
                    "productName": label_data.get('nazwa'),
                    "batchNumber": label_data.get('partia') or '---',
                    "productionDate": label_data.get('data') or datetime.now().strftime('%Y-%m-%d'),
                    "expiryDate": label_data.get('termin') or '---',
                    "currentWeight": label_data.get('ilosc'),
                    "labNotes": label_data.get('uwagi') or ""
                }
            }
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
        try:
            resp = requests.post(f"{self.bridge_url}/drukuj-zpl", json=payload, verify=False, timeout=5)
            if resp.status_code == 200 and resp.json().get('success'):
                return True, "Wysłano do drukarki przez mostek"
            return False, resp.json().get('message', 'Błąd mostka')
        except Exception as e:
            return False, f"Błąd komunikacji z mostkiem: {str(e)}"

# Singleton
_printer = None

def get_printer() -> PrintServer:
    global _printer
    if _printer is None:
        _printer = PrintServer()
    return _printer
