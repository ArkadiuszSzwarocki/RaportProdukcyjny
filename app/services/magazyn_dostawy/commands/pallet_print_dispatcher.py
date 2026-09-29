import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List


_PRINT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='pallet-print')


class PalletPrintDispatcher:
    """Dispatch physical ZPL jobs through the authenticated bridge client."""

    @classmethod
    def build_pallet_payload(cls, printer_name: str, printer_ip: str, pallet_type: str, item: Dict[str, Any], qty: float) -> Dict[str, Any]:
        return {
            'drukarka': printer_name,
            'ip': printer_ip,
            'typ': pallet_type,
            'copies': 2,
            'dane': {
                'palletData': {
                    'nrPalety': item.get('nr_palety'),
                    'productName': item.get('productName') or 'Brak nazwy',
                    'batchNumber': item.get('nr_partii') or '---',
                    'productionDate': str(item.get('data_produkcji')) if item.get('data_produkcji') else '---',
                    'expiryDate': str(item.get('data_przydatnosci')) if item.get('data_przydatnosci') else '---',
                    'currentWeight': qty,
                    'labNotes': 'Przyjęta',
                    'copies': 2,
                }
            },
        }

    @staticmethod
    def _run_queue(queue_payloads):
        from app.services.print_server import get_printer

        printer = get_printer()
        for payload in queue_payloads:
            printer._send_to_bridge(payload)  # pylint: disable=protected-access
            time.sleep(0.08)

    @classmethod
    def dispatch_print_queue(cls, payloads: List[Dict[str, Any]]) -> None:
        if payloads:
            _PRINT_EXECUTOR.submit(cls._run_queue, list(payloads))
