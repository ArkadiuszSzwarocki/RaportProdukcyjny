import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.scanner_service import ScannerService

def test_scanner_normalization():
    print("--- Testing Scanner _normalize_scanned_code ---")
    
    test_cases = [
        # Regular barcodes (just the code)
        ("SUR-123", "SUR-123"),
        ("R030102", "R030102"),
        ("MP01", "MP01"),
        ("OPK-99", "OPK-99"),
        ("PAL-12345", "PAL-12345"),
        ("123", "123"), # purely numeric barcode fallback
        
        # Barcodes with extra whitespace (Zebra scanner might add newline)
        ("SUR-430\n", "SUR-430"),
        ("  R050201 \r\n", "R050201"),
        
        # QR Codes (might contain URLs or extra prefixes/suffixes)
        ("https://raport.agro.pl/scanner?code=SUR-430", "SUR-430"),
        ("QR_PREFIX_R030102_SUFFIX", "R030102"),
        ("URL: http://example.com/scan/MP01", "MP01"),
        ("ANY_EXTRA_TEXT_SUR-999_END", "SUR-999"),
        
        # Lowercase should be uppercased
        ("sur-123", "SUR-123"),
        ("r030102", "R030102"),
        ("https://example.com?qr=sur-123", "SUR-123"),
        
        # Invalid or non-matching codes
        ("INVALID_CODE", "INVALID_CODE"), # Fallback to original if no token matched
        ("", ""),
    ]
    
    passed = 0
    for raw, expected in test_cases:
        result = ScannerService._normalize_scanned_code(raw)
        if result == expected:
            print(f"PASS: '{raw}' -> '{result}'")
            passed += 1
        else:
            print(f"FAIL: '{raw}' -> Expected '{expected}', got '{result}'")
            
    print(f"Passed {passed}/{len(test_cases)} tests.\n")

if __name__ == "__main__":
    test_scanner_normalization()
