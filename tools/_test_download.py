import requests,sys

try:
    r = requests.get('http://127.0.0.1:8082/api/test-pobierz-raport', timeout=10)
    print('status', r.status_code)
    print('content-disposition', r.headers.get('Content-Disposition'))
    print('len', len(r.content))
    open('raporty/_test_download.bin', 'wb').write(r.content)
    print('saved to raporty/_test_download.bin')
except Exception as e:
    print('error', type(e), e)
    sys.exit(1)
