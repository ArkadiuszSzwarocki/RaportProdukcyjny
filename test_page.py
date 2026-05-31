import sys
sys.path.insert(0, '.')
from app.core.factory import create_app

app = create_app()
app.config['TESTING'] = True
client = app.test_client()

with client.session_transaction() as sess:
    sess['_user_id'] = '1'

resp = client.get('/agro/magazyn')
print(f"Status: {resp.status_code}")
if resp.status_code == 500:
    print(resp.data.decode('utf-8'))
else:
    print(resp.data[:500])
