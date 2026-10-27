# cspell:words slownik
"""Order changes preserve stock and history and commit both linked orders together."""
import json
import sqlite3
from unittest.mock import patch, MagicMock
import pytest
from flask import Flask
from app.services.warehouse_order_changes import WarehouseOrderChanges, order_status
from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
from app.services.warehouse_order_service import WarehouseOrderService


class Database:
    def __init__(self, items=None):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.create_function('IF',3,lambda condition,yes,no: yes if condition else no)
        self.db.create_function('NOW',0,lambda: '2026-10-26 12:00:00')
        self.db.execute('CREATE TABLE magazyn_zamowienia(id INTEGER PRIMARY KEY,items TEXT,status TEXT,operator_login TEXT,komentarz TEXT,created_at TEXT,confirmed_at TEXT,magazynier_login TEXT)')
        self.db.execute('CREATE TABLE slownik_surowcow(nazwa TEXT)')
        self.db.execute("INSERT INTO slownik_surowcow VALUES ('Other material')")
        self.items = items or [dict(surowiec_nazwa='BM3', ilosc_kg=100, linia='AGRO')]
        self.db.execute("INSERT INTO magazyn_zamowienia(id,items,status) VALUES(1,?,'NOWE')", (json.dumps(self.items),))
        self.db.commit()
        self.sql = []
        self.fail_update = False
    def cursor(self, **kwargs):
        owner = self
        class Cursor:
            def execute(self, sql, args=()):
                owner.sql.append(sql)
                if owner.fail_update and sql.startswith('UPDATE'): raise RuntimeError('Simulated write failure')
                self.result = owner.db.execute(sql.replace('%s','?').replace(' FOR UPDATE',''),args)
                self.lastrowid = self.result.lastrowid
            def fetchone(self):
                row = self.result.fetchone()
                return dict(row) if row is not None else None
            def fetchall(self): return [dict(row) for row in self.result.fetchall()]
        return Cursor()
    def commit(self): self.db.commit()
    def rollback(self): self.db.rollback()
    def close(self): pass
    def rows(self): return [dict(row, items=json.loads(row['items'])) for row in self.db.execute('SELECT * FROM magazyn_zamowienia ORDER BY id')]
    def resolve(self, **payload):
        with patch('app.services.warehouse_order_changes.get_db_connection',return_value=self):
            return WarehouseOrderChanges.resolve(1,0,dict(mode='cancel',reason='Change approved',**payload),'approver','masteradmin')


def test_cancellation_keeps_partial_allocations_and_unaffected_lines():
    allocation = dict(kg=40,sscc='TEST',transfer_id='T',item_id='1')
    db = Database([dict(surowiec_nazwa='BM3',ilosc_kg=100,transfer_allocations=[allocation]), dict(surowiec_nazwa='Second',ilosc_kg=20)])
    assert db.resolve()[0]
    row = db.rows()[0]
    assert row['status'] == 'NOWE'
    item = row['items'][0]
    assert item['transfer_allocations'] == [allocation]
    assert item['cancellation']['cancelled_kg'] == 60
    assert item['cancellation']['login'] == 'approver'
    assert 'cancellation' not in row['items'][1]
    assert not any('magazyn_surowce' in sql for sql in db.sql)


def test_replacement_is_a_linked_new_order_not_fulfillment():
    db = Database()
    with patch('app.services.warehouse_order_changes.get_db_connection',return_value=db):
        result = WarehouseOrderChanges.resolve(1,0,dict(mode='replace',reason='Approved alternative',replacement_name='Other material',replacement_kg='75,5'),'approver','operator')
    assert result[0] and result[2] == 2
    old,new = db.rows()
    assert old['status'] == 'ANULOWANE' and new['status'] == 'NOWE'
    assert old['items'][0]['cancellation']['replacement_order_id'] == 2
    assert new['items'][0]['replaces']['order_id'] == 1
    assert new['items'][0]['ilosc_kg'] == 75.5
    assert new['items'][0]['linia'] == 'AGRO'
    assert not db.resolve()[0]
    assert len(db.rows()) == 2


def test_new_order_insert_rolls_back_if_original_order_update_fails():
    db = Database(); db.fail_update = True
    with patch('app.services.warehouse_order_changes.get_db_connection',return_value=db), pytest.raises(RuntimeError):
        WarehouseOrderChanges.resolve(1,0,dict(mode='replace',reason='Approved',replacement_name='Other material',replacement_kg=80),'approver','admin')
    assert len(db.rows()) == 1
    assert 'cancellation' not in db.rows()[0]['items'][0]


@pytest.mark.parametrize('payload', [dict(mode='cancel',reason=''),dict(mode='replace',reason='Approved',replacement_name='Unknown',replacement_kg=5),dict(mode='replace',reason='Approved',replacement_name='Other material',replacement_kg='NaN'),dict(mode='replace',reason='Approved',replacement_name='BM3',replacement_kg=5)])
def test_invalid_decisions_leave_orders_unchanged(payload):
    db = Database()
    with patch('app.services.warehouse_order_changes.get_db_connection',return_value=db):
        result = WarehouseOrderChanges.resolve(1,0,payload,'approver','masteradmin')
    assert not result[0]
    assert db.rows()[0]['items'] == db.items
    assert len(db.rows()) == 1


def test_fully_allocated_position_cannot_be_cancelled():
    db = Database([dict(surowiec_nazwa='BM3',ilosc_kg=100,transfer_allocations=[dict(kg=100)])])
    assert not db.resolve()[0]


def test_cancelled_position_cannot_receive_new_allocations():
    item = dict(surowiec_nazwa='BM3',ilosc_kg=100,cancellation=dict(reason='No longer required'))
    assert WarehouseOrderFulfillment.requested(item) == 0
    assert order_status([item]) == 'ANULOWANE'
    assert order_status([item,dict(ilosc_kg=5)]) == 'NOWE'


def test_cancelled_transfer_cleanup_does_not_reopen_cancelled_order():
    db = Database([dict(surowiec_nazwa='BM3',ilosc_kg=100,cancellation=dict(reason='Approved'),transfer_allocations=[dict(kg=40,sscc='X',transfer_id='T',item_id='1')])])
    # Simulate the database IF/NOW expression through a recording cursor.
    cursor = MagicMock()
    cursor.fetchall.return_value = db.rows()
    WarehouseOrderFulfillment.sync_transfer(cursor,'T',[],'AGRO','scanner')
    updates = [call for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
    assert len(updates) == 1
    assert updates[0].args[1][1] == 'ANULOWANE'
    assert json.loads(updates[0].args[1][0])[0]['cancellation']['reason'] == 'Approved'


def test_history_cannot_be_deleted_and_list_retains_original_item_indices():
    service = WarehouseOrderService();service._repository = MagicMock()
    service._repository.get_by_id.return_value = dict(items=[dict(cancellation=dict(reason='Approved'))])
    assert not service.delete_order(1,'masteradmin')[0]
    service._repository.delete.assert_not_called()
    service._repository.get_all.return_value = [dict(id=1,status='ANULOWANE',items=[dict(ilosc_kg=0),dict(ilosc_kg=100,cancellation=dict(reason='Approved',replacement_order_id=2))])]
    item = service.get_all_orders()[0]['items'][0]
    assert item['item_index'] == 1
    assert item['realizacja_status'] == 'ZAMIENIONE'


@pytest.mark.parametrize('role,code', [('operator',200),('masteradmin',200),('laborant',403)])
def test_decision_api_enforces_order_permissions(role,code):
    from app.blueprints.warehouse_v2 import warehouse_v2_bp
    app = Flask(__name__);app.secret_key='test';app.register_blueprint(warehouse_v2_bp)
    from app.core.function_permissions import register_function_permissions
    register_function_permissions(app)
    client = app.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola=role,login='approver')
    db = Database()
    with patch('app.services.warehouse_order_changes.get_db_connection',return_value=db):
        response = client.post('/warehouse-v2/api/orders/1/items/0/resolve',json=dict(mode='cancel',reason='Approved'))
    assert response.status_code == code
    assert response.json['success'] == (code == 200)


def test_later_scan_cannot_fulfill_cancelled_original_or_different_replacement_material():
    db = Database()
    with patch('app.services.warehouse_order_changes.get_db_connection',return_value=db):
        assert WarehouseOrderChanges.resolve(1,0,dict(mode='replace',reason='Approved',replacement_name='Other material',replacement_kg=60),'approver','masteradmin')[0]
    db.db.execute('CREATE TABLE magazyn_surowce(id INTEGER,nr_palety TEXT,nazwa TEXT,stan_magazynowy REAL)')
    db.db.execute("INSERT INTO magazyn_surowce VALUES(10,'TEST-SSCC','BM3',100)")
    with patch('app.services.magazyn_dostawy.commands.internal_transfer_processor.InternalTransferProcessor._find_active_pallet_by_sscc',return_value=(dict(id=10),'surowiec','magazyn_surowce')), patch(
            'app.services.magazyn_dostawy.commands.pallet_lock_manager.PalletLockManager.has_quality_or_manual_block',return_value=False):
        WarehouseOrderFulfillment.sync_transfer(db.cursor(),'T',[dict(id='1',nr_palety='TEST-SSCC',netWeight=100)],'AGRO','scanner')
    old,new = db.rows()
    assert old['status'] == 'ANULOWANE' and new['status'] == 'NOWE'
    assert not old['items'][0].get('transfer_allocations')
    assert not new['items'][0].get('transfer_allocations')
