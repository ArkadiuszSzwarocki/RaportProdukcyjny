#!/usr/bin/env python3
import requests
import time

session = requests.Session()

# Login
print("[1] Logging in...")
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)
print("[OK] Logged in\n")

# Get dashboard
print("[2] Getting dashboard...")
r = session.get('http://localhost:8082/?sekcja=Zasyp')

import re
plan_ids = re.findall(r'data-id="(\d+)"', r.text)
print(f"[OK] Found plans: {plan_ids}\n")

# Try to delete plan 472 (zaplanowane status)
plan_id = '472'
print(f"[3] Deleting plan {plan_id} (zaplanowane status)...")
r = session.post(
    f'http://localhost:8082/api/usun_plan_ajax/{plan_id}',
    headers={'Content-Type': 'application/json'},
    json={'data_powrotu': '2026-02-07'}
)
print(f"    Status: {r.status_code}")

try:
    j = r.json()
    print(f"    Success: {j.get('success')}")
    print(f"    Message: {j.get('message')}")
    if j.get('success'):
        print("[OK] DELETED SUCCESSFULLY!")
    else:
        print(f"[ERR] Failed: {j.get('message')}")
except Exception as e:
    print(f"[ERR] Could not parse response: {e}")
    print(f"    Raw: {r.text[:200]}")

# Check if plan is gone
print(f"\n[4] Refreshing dashboard...")
time.sleep(1)
r = session.get('http://localhost:8082/?sekcja=Zasyp')
plan_ids_after = re.findall(r'data-id="(\d+)"', r.text)
print(f"    Plans before: {plan_ids}")
print(f"    Plans after:  {plan_ids_after}")

if plan_id in plan_ids_after:
    print("[ERR] Plan still visible!")
else:
    print("[OK] PLAN DELETED!")
