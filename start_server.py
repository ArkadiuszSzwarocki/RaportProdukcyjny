#!/usr/bin/env python
"""Start server and wait"""
import subprocess
import time
import sys

try:
    print("[*] Starting Flask server...")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print(f"[OK] Server started with PID {proc.pid}")
    
    # Keep running
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("[!] Shutting down...")
        proc.terminate()
        
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
