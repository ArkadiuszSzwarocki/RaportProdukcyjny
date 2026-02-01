import requests,sys
try:
    r = requests.get('http://127.0.0.1:8082/api/test-pobierz-raport', timeout=10)
    print('status', r.status_code)
    print('headers:', {k:v for k,v in r.headers.items() if k.lower() in ('content-type','content-disposition')})
    print('len', len(r.content))
except Exception as e:
    print('error', type(e), e)
    sys.exit(1)
