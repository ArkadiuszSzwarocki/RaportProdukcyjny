import requests
import json

try:
    s = requests.Session()
    # Need to log in first
    login_data = {'username': 'admin', 'password': '123'} # dummy or check what is valid
    # or just try without login to see if it's 401. If it's 401, we won't see the 500.
    
    headers = {'X-Requested-With': 'XMLHttpRequest'}
    r = s.post('http://localhost:8082/leaves/usun_z_obsady/140', headers=headers)
    
    print(r.status_code)
    try:
        print(r.json())
    except:
        # print first 500 chars of HTML
        print(r.text[:5000])
except Exception as e:
    print(e)
