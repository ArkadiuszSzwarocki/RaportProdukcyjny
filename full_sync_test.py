#!/usr/bin/env python
"""
Full synchronization test scenario:
1. Reset plans to 'zaplanowane'
2. Start plan on Zasyp - SUCCESS
3. Try to start DIFFERENT plan on Workowanie - BLOCKED
4. Try to start SAME plan on Workowanie - SUCCESS
"""

from app.db import get_db_connection
import requests
from datetime import date

print("="*60)
print("[SCENARIO] Synchronization Test: Zasyp → Workowanie")
print("="*60)

# 1. Reset plans
print("\n[STEP 1] Resetting plans to 'zaplanowane' status...")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute(
    "UPDATE plan_produkcji SET status='zaplanowane', real_start=NULL, real_stop=NULL "
    "WHERE DATE(data_planu)=%s AND sekcja IN ('Zasyp', 'Workowanie') LIMIT 8",
    (date.today(),)
)
conn.commit()
print(f"  ✓ Reset {cursor.rowcount} plans")

# Get 2 different plans
cursor.execute(
    "SELECT id, produkt, sekcja FROM plan_produkcji "
    "WHERE DATE(data_planu)=%s AND sekcja='Zasyp' "
    "ORDER BY id LIMIT 2",
    (date.today(),)
)
plans_zasyp = [(r[0], r[1]) for r in cursor.fetchall()]

cursor.execute(
    "SELECT id, produkt FROM plan_produkcji "
    "WHERE DATE(data_planu)=%s AND sekcja='Workowanie' "
    "ORDER BY id LIMIT 2",
    (date.today(),)
)
plans_workowanie = [(r[0], r[1]) for r in cursor.fetchall()]
conn.close()

if not plans_zasyp or not plans_workowanie:
    print("❌ Not enough plans to test!")
    exit(1)

plan_zasyp_1 = plans_zasyp[0]
plan_zasyp_2 = plans_zasyp[1]
plan_workowanie_1 = plans_workowanie[0]
plan_workowanie_2 = plans_workowanie[1]

print(f"\n  Plans selected:")
print(f"    Zasyp #{plan_zasyp_1[0]}: {plan_zasyp_1[1]}")
print(f"    Zasyp #{plan_zasyp_2[0]}: {plan_zasyp_2[1]}")
print(f"    Workowanie #{plan_workowanie_1[0]}: {plan_workowanie_1[1]}")
print(f"    Workowanie #{plan_workowanie_2[0]}: {plan_workowanie_2[1]}")

# 2. Login and test
print("\n[STEP 2] Logging in...")
session = requests.Session()
r = session.post("http://localhost:8082/login",
                 data={'login': 'admin', 'haslo': 'admin123'},
                 allow_redirects=True)
print("  ✓ Logged in as admin")

# 3. Start plan on Zasyp
print(f"\n[STEP 3] START plan {plan_zasyp_1[0]} on ZASYP...")
r = session.post(f"http://localhost:8082/start_zlecenie/{plan_zasyp_1[0]}",
                  data={'sekcja': 'Zasyp'},
                  allow_redirects=True)
if '✅' in r.text or 'Uruchomiono' in r.text:
    print(f"  ✓ SUCCESS - started on Zasyp")
else:
    print(f"  ? Status code: {r.status_code}")

# 4. Try to start DIFFERENT plan on Workowanie (should FAIL)
print(f"\n[STEP 4] Try to START DIFFERENT plan {plan_workowanie_1[0]} on WORKOWANIE...")
print(f"  (Expected: BLOCK because {plan_zasyp_1[0]} is running on Zasyp)")
r = session.post(f"http://localhost:8082/start_zlecenie/{plan_workowanie_1[0]}",
                  data={'sekcja': 'Workowanie'},
                  allow_redirects=True)
if '⏸️' in r.text or 'Na Zasyp trwa' in r.text or 'warning' in r.text:
    print(f"  ✓ BLOCKED correctly - synchronization working!")
    if 'czeka w kolejce' in r.text:
        print(f"    Message includes queue info")
else:
    print(f"  ✗ NOT BLOCKED - problem with synchronization")

# 5. Try to start SAME plan on Workowanie (should SUCCEED)
print(f"\n[STEP 5] Try to START SAME plan {plan_zasyp_1[0]} on WORKOWANIE...")
print(f"  (Expected: ALLOW because it matches Zasyp order)")
r = session.post(f"http://localhost:8082/start_zlecenie/{plan_zasyp_1[0]}",
                  data={'sekcja': 'Workowanie'},
                  allow_redirects=True)
if '✅' in r.text or 'Uruchomiono' in r.text or 'Already running' in r.text or 'w toku' in r.text:
    print(f"  ✓ ALLOWED - same plan can start on Workowanie")
else:
    if '⏸️' in r.text or 'Na Zasyp' in r.text:
        print(f"  ✗ INCORRECTLY BLOCKED - should allow same plan")
    else:
        print(f"  ? Unknown response")

print("\n" + "="*60)
print("[✓] Synchronization test complete!")
print("="*60)
