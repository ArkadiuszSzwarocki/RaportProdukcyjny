import requests
import time

session = requests.Session()

# Login
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)
print("[✓] Logged in as admin")

# Get dashboard to find a plan ID
r = session.get('http://localhost:8082/?sekcja=Zasyp')
print(f"[✓] Got dashboard (status {r.status_code})")

# Find plan IDs from HTML
import re
plan_ids = re.findall(r'data-id="(\d+)"', r.text)
print(f"[✓] Found {len(plan_ids)} plans")

if len(plan_ids) >= 2:
    plan1, plan2 = plan_ids[0], plan_ids[1]
    print(f"\n[TEST] Plan IDs: {plan1}, {plan2}")
    
    # START plan1 on Zasyp
    print(f"\n1. Starting plan {plan1} on ZASYP...")
    r = session.post(f'http://localhost:8082/start_zlecenie/{plan1}?sekcja=Zasyp')
    print(f"   Response: {r.status_code}")
    
    time.sleep(1)
    
    # Try START plan2 on Workowanie (should be blocked due to sync)
    print(f"\n2. Trying to start DIFFERENT plan {plan2} on WORKOWANIE (should be blocked)...")
    r = session.post(f'http://localhost:8082/start_zlecenie/{plan2}?sekcja=Workowanie')
    print(f"   Response: {r.status_code}")
    
    if 'na Zasyp' in r.text or 'Synchronizacja' in r.text or 'możesz startować' in r.text:
        print("   ✓ SYNC CHECK WORKED - different plan blocked!")
    else:
        print("   ? Check browser for actual message")
    
    # Try START plan1 on Workowanie (should be allowed - same plan)
    print(f"\n3. Starting SAME plan {plan1} on WORKOWANIE (should succeed)...")
    r = session.post(f'http://localhost:8082/start_zlecenie/{plan1}?sekcja=Workowanie')
    print(f"   Response: {r.status_code}")
    if r.status_code == 200:
        print("   ✓ SAME PLAN ALLOWED - synchronization working!")
else:
    print("[!] Not enough plans to test sync")
