import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import requests

def main(base='http://localhost:8082'):
    try:
        r = requests.get(base + '/api/bufor', timeout=10)
        print('status', r.status_code)
        print(r.text[:2000])
    except Exception as e:
        print('ERROR', e)

if __name__ == '__main__':
    b = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8082'
    main(b)
