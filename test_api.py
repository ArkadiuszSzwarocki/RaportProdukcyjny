import sys
import os
import requests

url = "http://127.0.0.1:5000/magazyny-nowe/historia-stacji/data?linia=AGRO"
try:
    response = requests.get(url)
    data = response.json()
    if 'data' in data:
        print("Returned rows:", len(data['data']))
        for row in data['data'][:10]:
            print(row)
    else:
        print(data)
except Exception as e:
    print(e)
