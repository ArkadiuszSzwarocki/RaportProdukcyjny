from db import get_db_connection

conn = get_db_connection()
c = conn.cursor()
print('Last 20 users:')
c.execute("SELECT id, login, COALESCE(pracownik_id, 'NULL') FROM uzytkownicy ORDER BY id DESC LIMIT 20")
users = c.fetchall()
for u in users:
    print(u)

print('\nCandidates without pracownik_id and possible matches:')
for u in users:
    uid, login, pid = u[0], u[1], u[2]
    if pid is None or str(pid).upper()=='NULL':
        l_low = login.lower()
        c.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE LOWER(imie_nazwisko) LIKE %s LIMIT 5", (f'%{l_low}%',))
        matches = c.fetchall()
        print(f"\nUser: id={uid} login={login} -> matches: {matches}")

conn.close()
