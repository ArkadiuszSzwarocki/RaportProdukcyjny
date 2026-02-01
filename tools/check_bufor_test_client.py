import os
import sys
import importlib

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
mod = importlib.import_module('app')
flask_app = getattr(mod, 'app')

c = flask_app.test_client()
r = c.get('/api/bufor')
print('status', r.status_code)
try:
    print('json:', r.get_json())
except Exception:
    print('text:', r.data[:400])
