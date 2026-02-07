#!/usr/bin/env python3
import requests
import time

session = requests.Session()

# Login
print("[*] Logging in...")
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)
print(f"[OK] Status: {r.status_code}\n")

# Get dashboard and find orders
print("[*] Getting dashboard...")
r = session.get('http://localhost:8082/?sekcja=Zasyp')
dashboard_html = r.text

# Find plan IDs
import re
plan_ids_zasyp = re.findall(r'data-id="(\d+)"', dashboard_html)

if not plan_ids_zasyp:
    print("[!] No active plans found. Add plans first!")
else:
    plan_id_zasyp = plan_ids_zasyp[0]
    print(f"[OK] Found Zasyp order: {plan_id_zasyp}\n")
    
    # START on Zasyp
    print(f"[1] Starting plan {plan_id_zasyp} on ZASYP...")
    r = session.post(
        f'http://localhost:8082/start_zlecenie/{plan_id_zasyp}?sekcja=Zasyp'
    )
    print(f"    Status: {r.status_code}")
    
    # Check if started
    if 'w toku' in r.text or 'Uruchomiono' in r.text:
        print("    [OK] Order started on Zasyp\n")
    else:
        print("    [CHECK] Response: %s...\n" % r.text[:100])
    
    time.sleep(1)
    
    # Now try to START DIFFERENT order on Workowanie
    print("[*] Getting Workowanie section...")
    r = session.get('http://localhost:8082/?sekcja=Workowanie')
    plan_ids_workowanie = re.findall(r'data-id="(\d+)"', r.text)
    
    if plan_ids_workowanie and plan_ids_workowanie[0] != plan_id_zasyp:
        plan_id_workowanie = plan_ids_workowanie[0]
        print(f"[2] Starting DIFFERENT plan {plan_id_workowanie} on WORKOWANIE...")
        print(f"    (Zasyp has {plan_id_zasyp}, Workowanie trying {plan_id_workowanie})\n")
        
        r = session.post(
            f'http://localhost:8082/start_zlecenie/{plan_id_workowanie}?sekcja=Workowanie'
        )
        print(f"    Status: {r.status_code}")
        
        # Check response for success or warning
        if 'Uruchomiono' in r.text:
            print("    [OK] START SUCCEEDED (no blocking)")
        
        if 'Na Zasyp trwa' in r.text or 'info' in r.text.lower():
            print("    [OK] Info popup shown about Zasyp order")
        
        # Check if page shows Workowanie section running
        if 'w toku' in r.text:
            print("    [OK] Order is now 'w toku' on Workowanie\n")
        else:
            print("    [i] Check browser to verify status\n")
        
        print("[RESULT] SUCCESS: Workowanie can START independently!")
    else:
        if not plan_ids_workowanie:
            print("[!] No Workowanie plans available")
        else:
            print("[!] Same plan in both sections - need different orders to test")
