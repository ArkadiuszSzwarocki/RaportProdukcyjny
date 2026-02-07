import requests
import time

session = requests.Session()

# Login
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)
print("[OK] Logged in as admin")

# Get dashboard to find a plan ID
r = session.get('http://localhost:8082/?sekcja=Zasyp')
print("[OK] Got dashboard (status %d)" % r.status_code)

# Find plan IDs from HTML
import re
plan_ids = re.findall(r'data-id="(\d+)"', r.text)
print("[OK] Found %d plans" % len(plan_ids))

if len(plan_ids) >= 2:
    plan1, plan2 = plan_ids[0], plan_ids[1]
    print("\n[TEST] Plan IDs: %s, %s" % (plan1, plan2))
    
    # START plan1 on Zasyp
    print("\n1. Starting plan %s on ZASYP..." % plan1)
    r = session.post('http://localhost:8082/start_zlecenie/%s?sekcja=Zasyp' % plan1)
    print("   Response: %d" % r.status_code)
    
    time.sleep(1)
    
    # Try START plan2 on Workowanie (should be blocked due to sync)
    print("\n2. Trying to start DIFFERENT plan %s on WORKOWANIE (should be blocked)..." % plan2)
    r = session.post('http://localhost:8082/start_zlecenie/%s?sekcja=Workowanie' % plan2)
    print("   Response: %d" % r.status_code)
    
    if 'na Zasyp' in r.text or 'Synchronizacja' in r.text or 'to zlecenie' in r.text:
        print("   [OK] SYNC CHECK WORKED - different plan blocked!")
    else:
        print("   [CHECK] Response contains: %s..." % r.text[:100])
    
    # Try START plan1 on Workowanie (should be allowed - same plan)
    print("\n3. Starting SAME plan %s on WORKOWANIE (should succeed)..." % plan1)
    r = session.post('http://localhost:8082/start_zlecenie/%s?sekcja=Workowanie' % plan1)
    print("   Response: %d" % r.status_code)
    if r.status_code == 200:
        print("   [OK] SAME PLAN ALLOWED - synchronization working!")
else:
    print("[!] Not enough plans to test sync")
