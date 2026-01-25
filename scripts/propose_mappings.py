"""
Propose mappings between `uzytkownicy.login` and `pracownicy.imie_nazwisko` using simple heuristics.
Prints suggestions; does NOT modify DB.
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from db import get_db_connection

def normalize(s):
    return ''.join(c.lower() for c in s if c.isalnum())

def propose():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, login FROM uzytkownicy')
    users = cursor.fetchall()
    cursor.execute('SELECT id, imie_nazwisko FROM pracownicy')
    workers = cursor.fetchall()
    w_norm = [(w[0], w[1], normalize(w[1]), [t for t in normalize(w[1]).split()]) for w in workers]
    print('Proposed mappings (user -> worker):')
    for u in users:
        uid, login = u[0], u[1]
        n = normalize(login)
        # Heuristics: exact substring, first name token in login, or initials
        best = None
        # exact substring
        for w in w_norm:
            if n and n in w[2]:
                best = (w, 'exact')
                break
        if not best:
            for w in w_norm:
                tokens = w[2]
                for t in tokens:
                    if t and t in n:
                        best = (w, f'token:{t}')
                        break
                if best: break
        if not best:
            # initials match: take first letters of tokens
            for w in w_norm:
                initials = ''.join(t[0] for t in w[2].split() if t)
                if initials and initials in n:
                    best = (w, f'initials:{initials}')
                    break

        if best:
            w, reason = best
            print(f"{login} (id={uid})  ->  {w[1]} (id={w[0]})  [reason={reason}]")
        else:
            print(f"{login} (id={uid})  ->  (no suggestion)")
    conn.close()

if __name__ == '__main__':
    propose()
