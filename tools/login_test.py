import urllib.request, urllib.parse, http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
url='http://127.0.0.1:8082/login'
data = urllib.parse.urlencode({'login':'Admin','haslo':'Masterkey'}).encode()
req = urllib.request.Request(url, data=data, method='POST')
try:
    resp = opener.open(req, timeout=10)
    print('STATUS', resp.getcode())
    body = resp.read().decode('utf-8', errors='replace')
    print('HEAD', body[:400])
except urllib.error.HTTPError as e:
    print('HTTPERROR', e.code)
    try:
        print(e.read().decode('utf-8', errors='replace')[:400])
    except Exception:
        pass
print('COOKIES:')
for c in cj:
    print(c.name, c.value)
