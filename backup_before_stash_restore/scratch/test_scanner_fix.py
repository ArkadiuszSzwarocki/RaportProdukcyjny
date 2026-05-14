import sys
import os
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.scanner_service import ScannerService

def test_lookup():
    print("Testing lookup for MP01 in AGRO:")
    res = ScannerService.lookup_by_location('MP01', 'AGRO')
    if res:
        print(f"SUCCESS: Found pallet {res['nazwa']} at {res['lokalizacja']}")
    else:
        print("FAILURE: MP01 not found (Expected to find one of the floor pallets)")

    print("\nTesting lookup for SUR-430 in AGRO:")
    res = ScannerService.lookup_by_location('SUR-430', 'AGRO')
    if res:
        print(f"SUCCESS: Found pallet {res['nazwa']} by ID")
    else:
        print("FAILURE: SUR-430 not found")

if __name__ == "__main__":
    test_lookup()
