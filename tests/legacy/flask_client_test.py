import sys, os
sys.path.insert(0, os.path.abspath(''))
from app import app
from db import get_db_connection
from werkzeug.security import generate_password_hash

# ensure test user exists
login='test_jupiter5'
passwd='TestHaslo123'
conn=get_db_connection()
cur=conn.cursor()
cur.execute('SELECT COUNT(*) FROM uzytkownicy WHERE login=%s',(login,))
if cur.fetchone()[0]==0:
    cur.execute('INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s,%s,%s)',(login, generate_password_hash(passwd),'magazynier'))
    conn.commit()
cur.close(); conn.close()

with app.test_client() as c:
    # login
    rv = c.post('/login', data={'login':login,'haslo':passwd}, follow_redirects=True)
    print('login status', rv.status_code)
    # call summary (AJAX)
    rv2 = c.get('/api/wnioski/summary', headers={'X-Requested-With':'XMLHttpRequest'})
    print('summary status', rv2.status_code)
    print('summary data:', rv2.get_json())
