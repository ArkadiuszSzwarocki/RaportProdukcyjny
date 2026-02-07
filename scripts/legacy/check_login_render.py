import urllib.request

URL = 'http://127.0.0.1:8082/login'
try:
    with urllib.request.urlopen(URL, timeout=5) as r:
        html = r.read().decode('utf-8')
        i = html.find('<body')
        print('BODY_SNIPPET:')
        print(html[i:i+300])
except Exception as e:
    print('ERROR fetching', URL, e)
