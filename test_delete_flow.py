#!/usr/bin/env python3
import requests
import time

session = requests.Session()

# 1. Login
print("[1] Logging in...")
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)
if r.status_code != 200:
    print(f"[ERR] Login failed: {r.status_code}")
    exit(1)
print("[OK] Logged in\n")

# 2. Get dashboard to find plan IDs
print("[2] Getting dashboard...")
r = session.get('http://localhost:8082/?sekcja=Zasyp', allow_redirects=True)
if r.status_code != 200:
    print(f"[ERR] Dashboard failed: {r.status_code}")
    exit(1)

import re
plan_ids = re.findall(r'data-id="(\d+)"', r.text)
if not plan_ids:
    print("[!] No plans found in dashboard. Cannot test delete.\n")
    exit(0)

plan_id = plan_ids[0]
print(f"[OK] Found plan ID: {plan_id}\n")

# 3. DELETE the plan
print(f"[3] Deleting plan {plan_id}...")
r = session.post(
    f'http://localhost:8082/api/usun_plan_ajax/{plan_id}',
    headers={'Content-Type': 'application/json'},
    json={'data_powrotu': '2026-02-07'}
)
print(f"    Status: {r.status_code}")
print(f"    Response: {r.text[:200]}")

try:
    j = r.json()
    print(f"    JSON success: {j.get('success')}")
    print(f"    JSON message: {j.get('message')}")
    if j.get('success'):
        print("[OK] Backend deleted successfully!")
    else:
        print(f"[!] Backend returned success=False: {j.get('message')}")
except Exception as e:
    print(f"[ERR] Could not parse JSON: {e}")

# 4. Refresh and check if plan is gone
print(f"\n[4] Refreshing dashboard...")
time.sleep(1)
r = session.get('http://localhost:8082/?sekcja=Zasyp', allow_redirects=True)
plan_ids_after = re.findall(r'data-id="(\d+)"', r.text)
print(f"    Plans before: {plan_ids}")
print(f"    Plans after:  {plan_ids_after}")

if plan_id in plan_ids_after:
    print("[ERR] PLAN STILL VISIBLE - delete didn't work properly!")
else:
    print("[OK] PLAN IS GONE - delete worked!")
