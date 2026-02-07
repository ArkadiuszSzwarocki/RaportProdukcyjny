#!/usr/bin/env python3
import requests
from datetime import datetime, timedelta

BASE_URL = 'http://localhost:8082'
TODAY = datetime.now().strftime('%Y-%m-%d')
TOMORROW = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

session = requests.Session()

# Login
print(f'🔐 Logging in as admin...')
login_resp = session.post(f'{BASE_URL}/login', data={
    'username': 'admin',
    'password': 'admin123'
}, allow_redirects=True)
print(f'  Status: {login_resp.status_code}')
print(f'  Cookies: {session.cookies.get_dict()}')
print(f'  URL after redirect: {login_resp.url}')

# Get dashboard to see plans
print(f'\n📋 Fetching dashboard for {TODAY}...')
dash_resp = session.get(f'{BASE_URL}/', params={'data': TODAY, 'sekcja': 'Zasyp'})
print(f'  Status: {dash_resp.status_code}')
if dash_resp.status_code == 200:
    # Find planID with status 'zaplanowane'
    import re
    plan_ids = re.findall(r'data-id="(\d+)"', dash_resp.text)
    print(f'  Found plans: {plan_ids}')
    
    # Look for zaplanowane status
    zaplanowane = re.findall(r'data-id="(\d+)".*?row-zaplanowane', dash_resp.text, re.DOTALL)
    if zaplanowane:
        test_plan_id = zaplanowane[0]
        print(f'  Found zaplanowane plan: {test_plan_id}')
        
        # Try to DELETE it
        print(f'\n🗑️  Deleting plan {test_plan_id}...')
        delete_resp = session.post(f'{BASE_URL}/api/usun_plan_ajax/{test_plan_id}', 
            json={'data_powrotu': TODAY},
            headers={'Content-Type': 'application/json'}
        )
        print(f'  Status: {delete_resp.status_code}')
        print(f'  Response: {delete_resp.json()}')
        
        # Refresh and check if deleted
        print(f'\n🔄 Refreshing dashboard...')
        dash_resp2 = session.get(f'{BASE_URL}/', params={'data': TODAY, 'sekcja': 'Zasyp'})
        plan_ids_after = re.findall(r'data-id="(\d+)"', dash_resp2.text)
        print(f'  Plans after delete: {plan_ids_after}')
        
        if test_plan_id not in plan_ids_after:
            print(f'\n✅ SUCCESS: Plan {test_plan_id} deleted!')
        else:
            print(f'\n❌ FAILED: Plan {test_plan_id} still exists!')
    else:
        print('  No zaplanowane plans found on dashboard')
        print('  (This is the issue - plans not showing!)')
