import json
import pytest
from app.services.scanner_service import ScannerService

def test_scanner_service_normalizes_json_qr():
    """Testuje, czy ScannerService._normalize_scanned_code wyciąga czysty numer SSCC z kodu QR zawierającego JSON."""
    qr_payload = json.dumps({
        "sscc": "SUR180520269103527396",
        "prod": "KWAS CYTRYNOWY",
        "partia": "260818R300",
        "data_prod": "2026-08-18",
        "data_exp": "2027-08-18",
        "qty": 1000.0
    })

    extracted = ScannerService._normalize_scanned_code(qr_payload)
    assert extracted == "SUR180520269103527396"

def test_scanner_service_normalizes_agro_json_qr():
    """Testuje wyciąganie SSCC dla wyrobu gotowego AGRO z JSON."""
    qr_payload = json.dumps({
        "sscc": "AGR000001787139218902",
        "prod": "AGRO MILK TOP",
        "partia": "260818R300(30)MP01",
        "data_prod": "2026-08-18",
        "data_exp": "2027-08-18"
    })

    extracted = ScannerService._normalize_scanned_code(qr_payload)
    assert extracted == "AGR000001787139218902"

def test_scanner_service_normalizes_plain_sscc():
    """Testuje, czy zwykły kod SSCC lub ID nie jest modyfikowany."""
    assert ScannerService._normalize_scanned_code("SUR180520269103527396") == "SUR180520269103527396"
    assert ScannerService._normalize_scanned_code("AGR000001787139218902") == "AGR000001787139218902"
    assert ScannerService._normalize_scanned_code("R030102") == "R030102"
    assert ScannerService._normalize_scanned_code("(00)123456789012345678") == "123456789012345678"
