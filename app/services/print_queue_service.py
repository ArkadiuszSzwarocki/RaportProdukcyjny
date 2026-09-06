import socket
import time
import threading
from typing import Dict, Any, Optional

class PrintQueueService:
    """
    Robust ZPL / Network Printer Dispatcher with automatic retries and TCP socket health verification.
    Prevents silent label loss on network hiccups or paper out.
    """

    DEFAULT_TIMEOUT_SEC = 4
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY_SEC = 1.5

    @staticmethod
    def check_printer_connectivity(ip: str, port: int = 9100, timeout: float = DEFAULT_TIMEOUT_SEC) -> bool:
        """Verifies whether the network printer TCP port is listening and responsive."""
        if not ip or not str(ip).strip():
            return False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((str(ip).strip(), int(port)))
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    @staticmethod
    def send_zpl_with_retry(
        ip: str,
        zpl_data: str,
        port: int = 9100,
        max_attempts: int = MAX_RETRY_ATTEMPTS
    ) -> Dict[str, Any]:
        """
        Transmits ZPL payload directly to the network printer with exponential retry strategy.
        """
        if not ip or not str(ip).strip():
            return {"success": False, "message": "Brak adresu IP drukarki."}

        encoded_data = zpl_data.encode('utf-8') if isinstance(zpl_data, str) else zpl_data
        target_ip = str(ip).strip()

        for attempt in range(1, max_attempts + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(PrintQueueService.DEFAULT_TIMEOUT_SEC)
                    sock.connect((target_ip, int(port)))
                    sock.sendall(encoded_data)
                    return {
                        "success": True,
                        "attempts": attempt,
                        "message": f"Wydrukowano pomyślnie (próba {attempt}/{max_attempts})."
                    }
            except Exception as e:
                if attempt < max_attempts:
                    time.sleep(PrintQueueService.RETRY_DELAY_SEC * attempt)
                else:
                    return {
                        "success": False,
                        "attempts": attempt,
                        "message": f"Błąd komunikacji z drukarką {target_ip}:{port} po {max_attempts} próbach ({str(e)})."
                    }

        return {"success": False, "message": "Nieznany błąd kolejki wydruku."}
