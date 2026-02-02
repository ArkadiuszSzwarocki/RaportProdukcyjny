#!/usr/bin/env python3
"""
Test dodaj_plan function directly - without Flask server overhead
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Setup Flask app context
from app import app

# Create test app context
with app.app_context():
    print("[TEST] Flask app context created")
    
    # Try importing the route
    try:
        from routes_api import dodaj_plan
        print("[OK] dodaj_plan imported successfully")
    except Exception as e:
        print(f"[ERROR] Failed to import dodaj_plan: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print("[TEST] All imports OK")
