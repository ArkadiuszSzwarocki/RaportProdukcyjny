#!/usr/bin/env python3
"""
Test app startup with Flask development server instead of waitress
"""
from app import app

if __name__ == '__main__':
    print("[TEST] Starting Flask development server...")
    app.run(host='0.0.0.0', port=8082, debug=False)
