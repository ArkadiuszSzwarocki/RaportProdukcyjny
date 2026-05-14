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

import socket
import os
from datetime import datetime

try:
    import win32print
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


# ─────────────────────────────────────────────────────────────────────────────
# ZPL label templates
# ─────────────────────────────────────────────────────────────────────────────

ZPL_LOCATION_LABEL = """\
^XA
^CI28
^FO20,20^GB760,470,3^FS
^FO40,35^A0N,28,28^FDMagazyn Surowcow Agro^FS
^FO40,75^GB680,2,2^FS
^FO40,90^A0N,90,90^FD{lokalizacja}^FS
^FO40,200^A0N,36,36^FD{nazwa}^FS
^FO40,250^A0N,30,30^FDStan: {ilosc:.1f} kg^FS
^FO40,295^A0N,24,24^FDID: {id} | {data}^FS
^FO40,350^BQN,2,6^FDMA,{qr_data}^FS
^XZ
"""

ZPL_PALLET_LABEL = """\
^XA
^CI28
^FO20,20^GB760,470,3^FS
^FO40,35^A0N,28,28^FD{nazwa}^FS
^FO40,80^A0N,28,28^FDLokalizacja: {lokalizacja}^FS
^FO40,130^A0N,90,90^FD{ilosc:.1f} kg^FS
^FO40,235^A0N,22,22^FDID: SUR-{id}^FS
^FO40,265^A0N,22,22^FD{data}^FS
^FO400,150^BQN,2,7^FDMA,{qr_data}^FS
^XZ
"""


# ─────────────────────────────────────────────────────────────────────────────
# PrintServer
# ─────────────────────────────────────────────────────────────────────────────

class PrintServer:

    def __init__(self, mode: str = None, ip: str = None, port: int = 9100, printer_name: str = None):
        self.mode         = (mode or os.getenv('PRINTER_MODE', 'tcp')).lower()
        self.ip           = ip or os.getenv('PRINTER_IP', '127.0.0.1')
        self.port         = int(port or os.getenv('PRINTER_PORT', 9100))
        self.printer_name = printer_name or os.getenv('PRINTER_NAME', '')

    # ── public ──────────────────────────────────────────────────────────────

    def print_location_label(self, label_data: dict) -> tuple[bool, str]:
        """Drukuje etykietę lokalizacji (regału) z kodem QR."""
        zpl = ZPL_LOCATION_LABEL.format(**label_data)
        return self._send(zpl)

    def print_pallet_label(self, label_data: dict) -> tuple[bool, str]:
        """Drukuje etykietę palety/worka z kodem QR."""
        zpl = ZPL_PALLET_LABEL.format(**label_data)
        return self._send(zpl)

    def test_connection(self) -> tuple[bool, str]:
        """Sprawdza połączenie z drukarką."""
        try:
            if self.mode == 'tcp':
                with socket.create_connection((self.ip, self.port), timeout=3):
                    pass
                return True, f"Drukarka dostępna ({self.ip}:{self.port})"
            elif self.mode == 'windows' and HAS_WIN32:
                printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
                if self.printer_name in printers:
                    return True, f"Drukarka '{self.printer_name}' dostępna"
                return False, f"Drukarka '{self.printer_name}' nie znaleziona. Dostępne: {printers}"
            else:
                return False, f"Nieznany tryb: {self.mode}"
        except Exception as e:
            return False, f"Błąd połączenia: {e}"

    # ── private ─────────────────────────────────────────────────────────────

    def _send(self, zpl: str) -> tuple[bool, str]:
        try:
            if self.mode == 'tcp':
                return self._send_tcp(zpl)
            elif self.mode == 'windows':
                return self._send_windows(zpl)
            else:
                return False, f"Nieznany tryb: {self.mode}"
        except Exception as e:
            return False, f"Błąd drukowania: {e}"

    def _send_tcp(self, zpl: str) -> tuple[bool, str]:
        """Wysyła ZPL bezpośrednio przez TCP do drukarki Zebra (port 9100)."""
        with socket.create_connection((self.ip, self.port), timeout=5) as sock:
            sock.sendall(zpl.encode('utf-8'))
        return True, f"Wydrukowano (TCP {self.ip}:{self.port})"

    def _send_windows(self, zpl: str) -> tuple[bool, str]:
        """Drukuje przez Windows Spooler (win32print)."""
        if not HAS_WIN32:
            return False, "win32print niedostępny — zainstaluj: pip install pywin32"
        hprinter = win32print.OpenPrinter(self.printer_name)
        try:
            job = win32print.StartDocPrinter(hprinter, 1, ("ZPL Label", None, "RAW"))
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, zpl.encode('utf-8'))
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
        finally:
            win32print.ClosePrinter(hprinter)
        return True, f"Wydrukowano przez '{self.printer_name}'"


# Singleton — tworzony z ENV
_printer: PrintServer | None = None


def get_printer() -> PrintServer:
    global _printer
    if _printer is None:
        _printer = PrintServer()
    return _printer
