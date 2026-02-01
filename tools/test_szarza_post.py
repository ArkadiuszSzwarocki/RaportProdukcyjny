import urllib.request, urllib.parse, re, sys
base='http://127.0.0.1:8082'
try:
    r=urllib.request.urlopen(base+'/?sekcja=Zasyp', timeout=5)
    txt=r.read().decode('utf-8')
except Exception as e:
    print('ERR_FETCH_PAGE', e)
    sys.exit(1)

m=re.search(r"/api/szarza_page/(\d+)", txt)
if not m:
    print('NO_SZARZA_LINK')
    sys.exit(2)
plan_id=m.group(1)
print('FOUND_plan_id', plan_id)
post_url=base+f'/dodaj_palete/{plan_id}'
data=urllib.parse.urlencode({'waga_palety':'123','sekcja':'Zasyp'}).encode()
req=urllib.request.Request(post_url, data=data, headers={'X-Requested-With':'XMLHttpRequest'})
try:
    resp=urllib.request.urlopen(req, timeout=5)
    out=resp.read().decode('utf-8')
    print('STATUS', getattr(resp,'status', None))
    print('RESPONSE_BODY')
    print(out)
except Exception as e:
    print('ERR_POST', e)
    sys.exit(3)
