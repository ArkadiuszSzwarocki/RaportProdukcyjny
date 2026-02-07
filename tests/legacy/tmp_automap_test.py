from app import app
from db import get_db_connection

login='automap_test_1'
prac_name='AutoMap Tester 1'

# Insert pracownik
conn=get_db_connection(); c=conn.cursor()
c.execute("INSERT INTO pracownicy (imie_nazwisko, grupa) VALUES (%s,%s)", (prac_name,''))
conn.commit()
# Retrieve inserted id
c.execute("SELECT id FROM pracownicy WHERE imie_nazwisko=%s ORDER BY id DESC LIMIT 1", (prac_name,))
r=c.fetchone()
prac_id = int(r[0]) if r else None
print('Inserted pracownik id=', prac_id)

# Use test client to POST to admin endpoint as admin
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'
    resp = client.post('/admin/konto/dodaj', data={'login': login, 'haslo': 'password', 'rola': 'user', 'grupa': ''}, follow_redirects=True)
    print('POST status:', resp.status_code)
    print('Response snippet:', resp.data.decode('utf-8')[:300])

# Check created user
conn2 = get_db_connection(); c2 = conn2.cursor()
c2.execute("SELECT id, login, pracownik_id FROM uzytkownicy WHERE login=%s", (login,))
user = c2.fetchone()
print('user row:', user)
conn2.close()
