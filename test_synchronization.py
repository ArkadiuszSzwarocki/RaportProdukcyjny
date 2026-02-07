#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test synchronization between Zasyp and Workowanie sections.
- When Zasyp has active order, only same order can start on Workowanie
- Rest wait in queue
"""

import requests
from datetime import date

session = requests.Session()
base_url = "http://localhost:8082"

# Login as admin
login_data = {'login': 'admin', 'haslo': 'admin123'}
session.post(f"{base_url}/login", data=login_data, allow_redirects=True)

# Get dashboard to find some plans
resp = session.get(f"{base_url}/?sekcja=Zasyp&data={date.today()}", allow_redirects=True)

# Find order IDs from the page - look for start_zlecenie forms
import re
# Pattern: url_for('production.start_zlecenie', id=123)
plan_ids = re.findall(r"production\.start_zlecenie.*?id=(\d+)", resp.text)

if len(plan_ids) < 2:
    print("❌ Need at least 2 plans to test, found:", len(plan_ids))
    # Try alternative pattern
    plan_ids = re.findall(r'/start_zlecenie/(\d+)', resp.text)
    if len(plan_ids) < 2:
        print("❌ Still not enough plans")
        exit(1)

plan1_id = int(plan_ids[0])
plan2_id = int(plan_ids[1] if len(plan_ids) > 1 else plan_ids[0])

print(f"[*] Found plans: {plan1_id}, {plan2_id}")

# 1. Start first plan on ZASYP
print(f"\n[•] Starting plan {plan1_id} on ZASYP...")
r1 = session.post(f"{base_url}/start_zlecenie/{plan1_id}", 
                   data={'sekcja': 'Zasyp'}, 
                   allow_redirects=True)

if 'Uruchomiono' in r1.text or '✅' in r1.text:
    print("✓ Plan started on Zasyp")
else:
    print("? Plan start response:", r1.status_code)

# 2. Try to start DIFFERENT plan on WORKOWANIE (should be blocked)
print(f"\n[•] Trying to start DIFFERENT plan {plan2_id} on WORKOWANIE (should fail)...")
r2 = session.post(f"{base_url}/start_zlecenie/{plan2_id}",
                   data={'sekcja': 'Workowanie'},
                   allow_redirects=True)

if 'Na Zasyp trwa zlecenie' in r2.text or '⏸️' in r2.text:
    print("✓ Blocked correctly - warning shown")
    if 'czeka w kolejce' in r2.text:
        print("✓ Queue message shown")
else:
    print("✗ NOT blocked - synchronization NOT working!")
    print("  Response contains:", 'warning' if 'warning' in r2.text else 'no warning')

# 3. Try to start SAME plan on WORKOWANIE (should succeed)
print(f"\n[•] Trying to start SAME plan {plan1_id} on WORKOWANIE (should succeed)...")
r3 = session.post(f"{base_url}/start_zlecenie/{plan1_id}",
                   data={'sekcja': 'Workowanie'},
                   allow_redirects=True)

if '⏸️' in r3.text and 'Na Zasyp trwa' in r3.text:
    print("✗ Still blocked - something wrong with second check")
elif 'Uruchomiono' in r3.text or '✅' in r3.text or 'w toku' in r3.text:
    print("✓ Same plan allowed on Workowanie")
else:
    print("? Response:", r3.status_code)

print("\n[✓] Synchronization test completed!")
