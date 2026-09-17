import time
import threading
from typing import List, Dict, Any
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PalletPrintDispatcher:
    """Dispatches physical ZPL print jobs for incoming pallets in background threads."""

    @classmethod
    def build_pallet_payload(cls, printer_name: str, printer_ip: str, pallet_type: str, item: Dict[str, Any], qty: float) -> Dict[str, Any]:
        return {
            "drukarka": printer_name,
            "ip": printer_ip,
            "typ": pallet_type,
            "copies": 2,
            "dane": {
                "palletData": {
                    "nrPalety": item.get('nr_palety'),
                    "productName": item.get('productName') or 'Brak nazwy',
                    "batchNumber": item.get('nr_partii') or '---',
                    "productionDate": str(item.get('data_produkcji')) if item.get('data_produkcji') else '---',
                    "expiryDate": str(item.get('data_przydatnosci')) if item.get('data_przydatnosci') else '---',
                    "currentWeight": qty,
                    "labNotes": "Przyjęta",
                    "copies": 2
                }
            }
        }

    @classmethod
    def dispatch_print_queue(cls, payloads: List[Dict[str, Any]]) -> None:
        if not payloads:
            return

        def _run_queue(queue_payloads):
            url = "http://127.0.0.1:3001/drukuj-zpl"
            for p in queue_payloads:
                try:
                    requests.post(url, json=p, verify=False, timeout=5)
                except Exception:
                    pass
                time.sleep(0.08)

        threading.Thread(target=_run_queue, args=(payloads,), daemon=True).start()
