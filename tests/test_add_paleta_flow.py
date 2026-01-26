from app import app
from db import get_db_connection
from datetime import date

print('Starting local test: add paleta via Flask test_client')

# Ensure we have a plan_id
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT id FROM plan_produkcji LIMIT 1")
row = cursor.fetchone()
if row:
    plan_id = row[0]
    print('Using existing plan_id=', plan_id)
else:
    print('No plan found, inserting test plan')
    cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc) VALUES (%s, %s, %s, %s, %s, %s)", (str(date.today()), 'Workowanie', 'TEST_PRODUCT', 1000, 'w toku', 1))
    conn.commit()
    cursor.execute("SELECT id FROM plan_produkcji WHERE produkt=%s ORDER BY id DESC LIMIT 1", ('TEST_PRODUCT',))
    plan_id = cursor.fetchone()[0]
    print('Inserted plan_id=', plan_id)
conn.close()

with app.test_client() as client:
    # set session to logged in as admin
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'

    # GET the page (optional)
    resp_get = client.get(f'/api/dodaj_palete_page/{plan_id}')
    print('GET /api/dodaj_palete_page status:', resp_get.status_code)
    if resp_get.status_code != 200:
        print('GET content:', resp_get.data[:300])

    # POST to add paleta
    data = {
        'waga_palety': '123',
        'sekcja': 'Workowanie'
    }
    resp = client.post(f'/api/dodaj_palete/{plan_id}', data=data, follow_redirects=True)
    print('POST /api/dodaj_palete status:', resp.status_code)
    # print a small part of response body
    print('Response length:', len(resp.data))
    print('Done')
