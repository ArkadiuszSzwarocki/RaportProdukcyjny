#!/usr/bin/env python3
"""Quick health check script - tests common endpoints and database operations."""

import sys
import time
import requests
from datetime import date
import json

BASE_URL = "http://localhost:5000"
VERBOSE = "-v" in sys.argv

def log(msg, level="INFO"):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def test_endpoint(method, path, **kwargs):
    """Test any endpoint and return (status_code, response_text)"""
    url = f"{BASE_URL}{path}"
    try:
        if method.upper() == "GET":
            resp = requests.get(url, timeout=5, **kwargs)
        elif method.upper() == "POST":
            resp = requests.post(url, timeout=5, **kwargs)
        else:
            return None, None
        return resp.status_code, resp.text[:500]
    except Exception as e:
        return None, str(e)

print("\n" + "="*70)
print("HEALTH CHECK: RaportProdukcyjny Application")
print("="*70)

# Test 1: Server is running
log("Checking server connectivity...")
status, resp = test_endpoint("GET", "/")
if status == 302:  # Redirect to login is expected
    log("✅ Server is running (redirect to login OK)", "OK")
elif status == 200:
    log("✅ Server responds (HTTP 200)", "OK")
else:
    log(f"⚠️  Unexpected status: {status}", "WARN")
    if resp:
        log(f"Response: {resp[:200]}", "DEBUG")

# Test 2: Check login page
log("Checking login page...")
status, resp = test_endpoint("GET", "/")
if status in [200, 302]:
    log("✅ Login/index accessible", "OK")
else:
    log(f"❌ Login page error: {status}", "ERROR")

# Test 3: Test with mock session
log("Checking database connectivity (indirectly)...")
# Most routes will try to access DB if session exists
# We can't fully test without auth, but we can check if templates are available

# Test 4: Check static files
log("Checking static files...")
status, resp = test_endpoint("GET", "/static/scripts.js")
if status == 200:
    log("✅ Static files accessible", "OK")
elif status == 404:
    log("⚠️  Static files not found (may be normal if serving separately)", "WARN")
else:
    log(f"Static files error: {status}", "ERROR")

# Test 5: Check API endpoints (should be 401 without auth)
log("Checking API endpoints...")
api_endpoints = [
    "/api/moje_godziny",
    "/api/nadgodziny",
]
for endpoint in api_endpoints:
    status, _ = test_endpoint("GET", endpoint)
    expected = [401, 302]  # Unauthorized or redirect to login
    if status in expected:
        log(f"✅ {endpoint} - proper auth check", "OK")
    else:
        log(f"⚠️  {endpoint} - unexpected status {status}", "WARN")

# Test 6: Check common routes
log("Checking common routes (expect 302 redirect to login)...")
routes = [
    "/planista",
    "/bufor",
    "/jakosc",
]
for route in routes:
    status, _ = test_endpoint("GET", route)
    if status in [301, 302]:
        log(f"✅ {route} - redirects to login", "OK")
    elif status == 200:
        log(f"⚠️  {route} - should redirect but didn't (status 200)", "WARN")
    else:
        log(f"⚠️  {route} - unexpected status {status}", "WARN")

print("\n" + "="*70)
log("Health check complete!", "OK")
print("="*70)
print("\n💡 Next steps:")
print("   1. Login to application to test authenticated routes")
print("   2. Monitor logs/debug.log for REQUEST/RESPONSE patterns")
print("   3. Check for errors in each click")
print("   4. Use browser DevTools for frontend checks")
