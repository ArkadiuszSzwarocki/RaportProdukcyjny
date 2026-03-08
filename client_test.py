import traceback
from app.core.factory import create_app

app = create_app()

# Disable Catching Exceptions so we get the raw unhandled traceback
app.config['TESTING'] = True
app.testing = True

try:
    with app.test_client() as client:
        # Mock login session
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['rola'] = 'lider'
            sess['login'] = 'admin'

        response = client.post('/leaves/usun_z_obsady/140', headers={'X-Requested-With': 'XMLHttpRequest'})
        
        print("Status code:", response.status_code)
        if response.status_code == 500:
            print("Response:", response.data.decode('utf-8'))
except Exception as e:
    print("Caught Unhandled Exception from Flask Test Client:")
    traceback.print_exc()
