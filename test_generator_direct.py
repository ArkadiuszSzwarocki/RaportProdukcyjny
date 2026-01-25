#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
from datetime import date, datetime

print("[TEST] Starting direct generator test")
print(f"[TEST] Python version: {sys.version}")
print(f"[TEST] Working dir: {os.getcwd()}")

# Test imports
try:
    from db import get_db_connection
    print("[TEST] ✓ db module imported")
except Exception as e:
    print(f"[TEST] ✗ Failed to import db: {e}")
    sys.exit(1)

try:
    from generator_raportow import generuj_paczke_raportow
    print("[TEST] ✓ generator_raportow module imported")
except Exception as e:
    print(f"[TEST] ✗ Failed to import generator_raportow: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test function call
try:
    date_str = "2026-01-25"
    uwagi = "Test uwagi"
    print(f"\n[TEST] Calling generuj_paczke_raportow('{date_str}', '{uwagi}')")
    result = generuj_paczke_raportow(date_str, uwagi)
    print(f"[TEST] ✓ Function returned: {result}")
    
    xls_path, txt_path, pdf_path = result
    print(f"[TEST] Excel: {xls_path} - exists: {os.path.exists(xls_path) if xls_path else 'N/A'}")
    print(f"[TEST] TXT: {txt_path} - exists: {os.path.exists(txt_path) if txt_path else 'N/A'}")
    print(f"[TEST] PDF: {pdf_path} - exists: {os.path.exists(pdf_path) if pdf_path else 'N/A'}")
    
except Exception as e:
    print(f"[TEST] ✗ Error calling generator:")
    print(f"[TEST] {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[TEST] ✓ All tests passed!")
