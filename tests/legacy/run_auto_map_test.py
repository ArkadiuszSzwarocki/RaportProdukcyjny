import sys,os
sys.path.insert(0, os.path.abspath('.'))
from db import get_db_connection
from werkzeug.security import generate_password_hash
import urllib.request, urllib.parse, http.cookiejar

login='test_jupiter5'
passwd='TestHaslo123'
conn=get_db_connection()
cur=conn.cursor()
cur.execute('SHOW COLUMNS FROM uzytkownicy')
cols=cur.fetchall()
print('columns:', cols)
# Insert user
cur.execute('SELECT COUNT(*) FROM uzytkownicy WHERE login=%s', (login,))
if cur.fetchone()[0]==0:
    h=generate_password_hash(passwd)
    cur.execute('INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s,%s,%s)', (login, h, 'magazynier'))
    conn.commit()
    print('Inserted user', login)
else:
    print('User exists')
cur.execute('SELECT id, login, pracownik_id FROM uzytkownicy WHERE login=%s', (login,))
print('before login:', cur.fetchone())
cur.close()
conn.close()

# Perform HTTP login to local app and then GET / to trigger mapping
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:
    data = urllib.parse.urlencode({'login':login,'haslo':passwd}).encode('utf-8')
    r = opener.open('http://127.0.0.1:8082/login', data=data, timeout=10)
    print('POST /login status', r.getcode())
    r2 = opener.open('http://127.0.0.1:8082/', timeout=10)
    print('GET / status', r2.getcode())
except Exception as e:
    print('HTTP error:', e)
    # Fallback: directly attempt the same auto-mapping logic as in app.before_request
    try:
        import re
        conn = get_db_connection()
        cur = conn.cursor()
        l = login.lower()
        l_alpha = re.sub(r"[^a-ząćęłńóśżź ]+", ' ', l)
        tokens = [t.strip() for t in re.split(r"\s+|[_\.\-]", l_alpha) if t.strip()]
        print('tokens:', tokens)
        if tokens:
            where_clauses = " AND ".join(["LOWER(imie_nazwisko) LIKE %s" for _ in tokens])
            params = tuple([f"%{t}%" for t in tokens])
            q = f"SELECT id FROM pracownicy WHERE {where_clauses} LIMIT 2"
            cur.execute(q, params)
            rows = cur.fetchall()
            print('candidate pracownicy rows:', rows)
            if len(rows) == 1:
                prac_id = int(rows[0][0])
                cur.execute('UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s', (prac_id, login))
                conn.commit()
                print('Auto-mapped', login, '->', prac_id)
            else:
                print('No unique match; skipping update')
        cur.close()
        conn.close()
    except Exception as e2:
        print('Fallback mapping error:', e2)

# Check DB after login
conn=get_db_connection()
cur=conn.cursor()
cur.execute('SELECT id, login, pracownik_id FROM uzytkownicy WHERE login=%s', (login,))
print('after login:', cur.fetchone())
cur.close(); conn.close()
