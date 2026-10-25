# cspell:words executemany
import unittest
from unittest.mock import patch
from app.services import warehouse_live_updates as live
class Cursor:
    rowcount=1
    def execute(self,*a,**k): return 'executed'
    def executemany(self,*a,**k): return 'executed-many'
class Connection:
    _autocommit=False
    def __init__(self): self.fail=False;self.last=None
    def cursor(self,*a,**k): self.last=Cursor();return self.last
    def commit(self):
        if self.fail: raise RuntimeError('commit failed')
        return 'committed'
    def rollback(self): return 'rolled back'
class Tests(unittest.TestCase):
    def setUp(self):
        self.publisher=patch.object(live,'publish');self.publish=self.publisher.start();self.addCleanup(self.publisher.stop)
        self.conn=live.observe_connection(Connection(),'test-db')
    def test_commit_notification(self):
        self.conn.cursor().execute('UPDATE magazyn_surowce SET waga=1')
        self.publish.assert_not_called();self.assertEqual(self.conn.commit(),'committed');self.publish.assert_called_once_with('test-db')
        self.conn.commit();self.publish.assert_called_once()
    def test_rollback(self):
        self.conn.cursor().execute('DELETE FROM magazyn_palety WHERE id=1');self.conn.rollback();self.conn.commit();self.publish.assert_not_called()
    def test_failed_commit(self):
        self.conn.cursor().execute('INSERT INTO palety_agro (id) VALUES (1)');self.conn.fail=True
        with self.assertRaises(RuntimeError): self.conn.commit()
        self.publish.assert_not_called()
    def test_reads_and_notifications(self):
        for sql in ['SELECT * FROM magazyn_palety','INSERT INTO powiadomienia (id) VALUES (1)','UPDATE aktywne_sesje SET id=1']:
            self.conn.cursor().execute(sql);self.conn.commit()
        self.publish.assert_not_called()
    def test_zero_rows(self):
        cursor=self.conn.cursor();cursor.rowcount=0;cursor.execute('UPDATE magazyn_palety SET id=1');self.conn.commit();self.publish.assert_not_called()
    def test_multiple_writes_one_commit(self):
        cursor=self.conn.cursor();cursor.execute('UPDATE magazyn_palety SET id=1');cursor.executemany('INSERT INTO magazyn_ruch VALUES (%s)',[(1,),(2,)])
        self.conn.commit();self.publish.assert_called_once()
    def test_autocommit(self):
        self.conn._autocommit=True;self.conn.cursor().execute('DELETE FROM magazyn_surowce WHERE id=1');self.publish.assert_called_once()
    def test_observer_idempotent(self):
        self.assertIs(live.observe_connection(self.conn,'test-db'),self.conn)
        self.conn.cursor().execute('UPDATE magazyn_surowce SET id=1');self.conn.commit();self.publish.assert_called_once()
    def test_stream_does_not_emit_repeated_revision(self):
        with patch.object(live,'revision',return_value='abc'), patch.object(live,'_WAKE'), patch.object(live.time,'monotonic',side_effect=[0,0,0,1,3,5,6]):
            self.assertEqual(len(list(live.stream('test-db',duration=4))),1)
    def test_notification_failure_keeps_commit(self):
        self.publish.side_effect=OSError('disk error');self.conn.cursor().execute('UPDATE magazyn_surowce SET id=1')
        with self.assertLogs(live.__name__,level='ERROR'): self.assertEqual(self.conn.commit(),'committed')
if __name__=='__main__': unittest.main(verbosity=2)


def test_shared_revision_between_processes_and_databases(tmp_path, monkeypatch):
    import subprocess, sys
    monkeypatch.setenv('WAREHOUSE_EVENT_DIR', str(tmp_path))
    before = live.revision('test-a')
    subprocess.run([sys.executable, '-c', "from app.services.warehouse_live_updates import publish; publish('test-a')"], check=True)
    assert live.revision('test-a') != before
    assert live.revision('test-b') == '0'


def test_stream_slots_reserve_http_capacity(monkeypatch):
    monkeypatch.setenv('GUNICORN_THREADS', '4')
    first, second = live.reserve_stream(), live.reserve_stream()
    assert first and second
    assert live.reserve_stream() is None
    first();first()
    third = live.reserve_stream()
    assert third
    second();third()
    assert live._STREAM_COUNT == 0


def test_real_mysql_cursor_and_pooled_connection_keep_connector_behavior():
    from mysql.connector.connection import MySQLConnection
    from mysql.connector.cursor import MySQLCursor
    from mysql.connector.pooling import PooledMySQLConnection, MySQLConnectionPool
    real = MySQLConnection()
    cursor = MySQLCursor(real)
    cursor._rowcount = 1
    pool = object.__new__(MySQLConnectionPool)
    conn = PooledMySQLConnection(pool, real)
    with patch.object(real, 'cursor', return_value=cursor), patch.object(real, 'commit') as commit, patch.object(real, 'rollback'), patch.object(cursor, 'execute', return_value=None), patch.object(cursor, 'executemany', return_value=None), patch.object(live, 'publish') as publish:
        assert live.observe_connection(conn, 'mysql-pool') is conn
        assert conn._cnx is real
        conn.cursor(dictionary=True).execute('UPDATE magazyn_palety SET waga_netto=1')
        conn.commit()
        commit.assert_called_once()
        publish.assert_called_once_with('mysql-pool')


def test_comments_and_qualified_identifiers_publish():
    conn = live.observe_connection(Connection(), 'test')
    with patch.object(live, 'publish') as publish:
        conn.cursor().execute('/* stock */ UPDATE `biblioteka`.`magazyn_palety` SET waga_netto=1')
        conn.commit()
        publish.assert_called_once_with('test')


def test_snapshot_is_read_only_and_fails_closed(monkeypatch):
    from flask import Flask
    from app.blueprints.warehouse_v2.controllers import warehouse_index_controller as module
    from unittest.mock import MagicMock
    app = Flask(__name__)
    conn = MagicMock()
    conn.cursor.return_value.execute.side_effect = RuntimeError('database query failed')
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(module.DashboardService, 'get_expiring_pallets', lambda *a, **k: [])
    with app.test_request_context('/warehouse-v2/api/live/snapshot?linia=ALL'):
        response, code = module.WarehouseIndexController.render_index(as_json=True)
        assert code == 503
        assert not response.get_json()['success']
        conn.commit.assert_not_called()
        conn.close.assert_called_once()


def test_live_endpoints_require_session_and_keep_snapshot_errors(monkeypatch):
    from flask import Flask, jsonify
    from app.blueprints.warehouse_v2 import warehouse_v2_bp
    from app.blueprints.warehouse_v2.views import WarehouseIndexController
    app = Flask(__name__)
    app.secret_key = 'test'
    app.register_blueprint(warehouse_v2_bp)
    with app.test_client() as client:
        for path in ['/warehouse-v2/api/live/events', '/warehouse-v2/api/live/snapshot']:
            assert client.get(path, headers={'Accept':'application/json'}).status_code == 401
        with client.session_transaction() as state:
            state.update(zalogowany=True, login='test', rola='pracownik')
        monkeypatch.setattr(WarehouseIndexController, 'render_index', lambda **kw: (jsonify(success=False), 503))
        response = client.get('/warehouse-v2/api/live/snapshot')
        assert response.status_code == 503
        assert response.headers['Cache-Control'] == 'no-store'
        with patch.object(live, 'stream', return_value=iter(['event: warehouse-change\ndata: abc\n\n'])):
            response = client.get('/warehouse-v2/api/live/events')
            assert response.status_code == 200
            assert response.mimetype == 'text/event-stream'
            response.close()
        assert live._STREAM_COUNT == 0
