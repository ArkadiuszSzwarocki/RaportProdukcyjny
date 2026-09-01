import unittest
import sys
sys.path.insert(0, '.')
from flask import session
from app.core.factory import create_app

class TestZasypPermissions(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def test_magazynier_can_access_szarza_page(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 12
            sess['login'] = 'BurzyMat'
            sess['rola'] = 'magazynier'
            sess['imie_nazwisko'] = 'Mateusz Burzykowski'

        # Fetch zasyp_page for a dummy plan_id or active plan_id
        # Check that it doesn't return redirect to '/' with flash warning
        response = self.client.get('/zasyp_page/4560?linia=PSD')
        # If plan exists or not, it should NOT flash "Brak uprawnień do dodawania zasypów"
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            perm_flashes = [msg for cat, msg in flashes if 'Brak uprawnień do dodawania zasypów' in msg]
            self.assertEqual(len(perm_flashes), 0, f"Flash error found: {perm_flashes}")

if __name__ == '__main__':
    unittest.main()
