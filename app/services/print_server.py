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
        """Wysyła dane palety do mostka, który wygeneruje ZPL 4x6."""
        nr_palety = (label_data.get('nr_palety') or label_data.get('nrPalety') or '').strip()
        if not nr_palety:
            from app.utils.pallet_id import generate_pallet_id
            nr_palety = generate_pallet_id('AGRO', type='surowiec', record_id=label_data.get('id'))

        payload = {
            "drukarka": override_name or self.printer_name,
            "ip": override_ip or self.printer_ip,
            "typ": "raw_material",
            "dane": {
                "palletData": {
                    "nrPalety": nr_palety,
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

    def print_finished_product_label(self, label_data: dict, override_ip: str | None = None, override_name: str | None = None) -> tuple[bool, str]:
        """Wysyła dane palety wyrobu gotowego do mostka ZPL 4x6 z kodem QR."""
        nr_palety = (label_data.get('nrPalety') or label_data.get('nr_palety') or '').strip()
        payload = {
            "drukarka": override_name or self.printer_name,
            "ip": override_ip or self.printer_ip,
            "typ": "finished_product",
            "dane": {
                "palletData": {
                    "nrPalety": nr_palety,
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
