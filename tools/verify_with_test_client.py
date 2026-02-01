import os
import sys
import importlib

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
try:
    mod = importlib.import_module('app')
except Exception as e:
    print('LOAD_ERR', repr(e))
    raise

flask_app = getattr(mod, 'app', None)
if flask_app is None:
    print('NO_APP_VAR in app.py')
    raise SystemExit(1)

c = flask_app.test_client()
try:
    r = c.get('/api/test-pobierz-raport')
    print('status', r.status_code)
    print('content-type', r.headers.get('Content-Type'))
    print('len', len(r.data))
    print('data_preview', r.data[:200])
except Exception as e:
    print('REQ_ERR', repr(e))
