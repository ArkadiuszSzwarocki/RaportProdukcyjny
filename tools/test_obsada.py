import requests

URL = 'http://127.0.0.1:8082/api/obsada_page?sekcja=Workowanie'
try:
    r = requests.get(URL, timeout=5)
    print('Status:', r.status_code)
    txt = r.text
    print('Len:', len(txt))
    idx = txt.find('class="section-box"')
    if idx != -1:
        print('FOUND .section-box at', idx)
    else:
        print('NO .section-box found')
    # print snippet
    print('\n----SNIPPET----\n')
    print(txt[:1000])
except Exception as e:
    print('ERROR', e)
