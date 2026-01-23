import importlib
import sys
import os
import pytest

# Ensure repository root on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import db


class DummyCursor:
    def __init__(self):
        self.execs = []
    def execute(self, sql, params=None):
        self.execs.append(str(sql))
    def fetchone(self):
        return None
    def fetchall(self):
        return []
    def close(self):
        pass


class DummyConn:
    def __init__(self):
        self.cursor_obj = DummyCursor()
        self.committed = False
    def cursor(self):
        return self.cursor_obj
    def commit(self):
        self.committed = True
    def close(self):
        pass


def test_zamknij_zmiane_monkeypatched(monkeypatch):
    # Podstawiamy testową "bazę" zanim zaimportujemy aplikację
    dummy = DummyConn()
    monkeypatch.setattr(db, 'get_db_connection', lambda: dummy)

    # Import app after monkeypatching DB
    app = importlib.import_module('app').app

    # Zamockuj generatory raportu i Outlook
    import generator_raportow
    monkeypatch.setattr(generator_raportow, 'generuj_excel_zmiany', lambda d: 'raport_fake.xlsx')
    monkeypatch.setattr(generator_raportow, 'otworz_outlook_z_raportem', lambda p, u: True)

    app.testing = True
    client = app.test_client()

    # Ustaw sesję zalogowanego
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'

    resp = client.post('/zamknij_zmiane', data={'uwagi_lidera': 'test'}, follow_redirects=False)

    # Powinien nastąpić redirect do /login
    assert resp.status_code in (302,)
    assert '/login' in (resp.headers.get('Location') or '')

    # Sprawdźmy, że wykonano UPDATE i INSERT
    executed = ' '.join(dummy.cursor_obj.execs)
    assert 'UPDATE plan_produkcji' in executed
    assert 'INSERT INTO raporty_koncowe' in executed
