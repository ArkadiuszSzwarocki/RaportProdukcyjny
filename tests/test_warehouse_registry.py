# cspell:words sscc pytestmark
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from app.db import get_db_connection
from app.services.warehouse_registry import WarehouseRegistry

pytestmark = pytest.mark.require_db


def test_migration_refuses_production_database():
    cursor = MagicMock()
    cursor.fetchone.return_value = {'name': 'biblioteka'}
    with pytest.raises(ValueError, match='kopii'):
        WarehouseRegistry.create_schema(cursor)
    assert cursor.execute.call_count == 1


def test_conflicts_stop_migration_before_writes(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(WarehouseRegistry, 'assert_copy', lambda cursor: None)
    monkeypatch.setattr(WarehouseRegistry, 'inventory', lambda cursor: ([], [{'reason': 'duplicate_sscc'}]))
    assert not WarehouseRegistry.migrate(connection)['ready']
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_migration_keeps_two_sscc_with_same_old_id_and_reconciles(monkeypatch):
    records = [dict(sscc='TEST-MIGRATION-' + uuid.uuid4().hex, kind=kind,
                    product_name='Test', quantity='100', unit='kg', location='MS01', hall='AGRO',
                    blocked=False, metadata='{}', source_table=table, source_id=1)
               for kind, table in [('raw', 'magazyn_surowce'), ('finished', 'magazyn_palety')]]
    monkeypatch.setattr(WarehouseRegistry, 'inventory', lambda cursor: (records, []))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    WarehouseRegistry.create_schema(cursor)
    try:
        result = WarehouseRegistry.migrate(conn)
        assert result['ready'] and result['reconciliation']['equal']
        cursor.execute('SELECT id,sscc,source_id FROM warehouse_pallets WHERE sscc IN (%s,%s)', tuple(row['sscc'] for row in records))
        migrated = cursor.fetchall()
        assert len({row['id'] for row in migrated}) == 2
        assert {row['source_id'] for row in migrated} == {1}
    finally:
        for record in records:
            cursor.execute('DELETE FROM warehouse_pallets WHERE sscc=%s', (record['sscc'],))
        conn.commit()
        conn.close()


@pytest.fixture
def registry_stock():
    code = 'TEST-REGISTRY-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    WarehouseRegistry.create_schema(cursor)
    cursor.execute("INSERT INTO warehouse_pallets(sscc,kind,product_name,quantity,unit,location,hall,metadata,source_table,source_id) VALUES(%s,'raw','Test',100,'kg','MS01','AGRO','{}','magazyn_surowce',1)", (code,))
    conn.commit()
    conn.close()
    yield code
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM warehouse_events WHERE pallet_id IN (SELECT id FROM warehouse_pallets WHERE sscc=%s)', (code,))
    cursor.execute('DELETE FROM warehouse_pallets WHERE sscc=%s', (code,))
    conn.commit()
    conn.close()


def test_one_movement_and_retry_keep_identity_and_quantity(registry_stock):
    conn = get_db_connection()
    arguments = dict(sscc=registry_stock, source='MS01', destination='OSIP', operation_key=uuid.uuid4().hex, operator='pytest')
    try:
        identity = WarehouseRegistry.move(conn, **arguments)
        assert WarehouseRegistry.move(conn, **arguments) == identity
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT location,quantity,version FROM warehouse_pallets WHERE sscc=%s', (registry_stock,))
        row = cursor.fetchone()
        assert row['location'] == 'OSIP' and row['quantity'] == 100 and row['version'] == 1
        cursor.execute('SELECT COUNT(*) AS total FROM warehouse_events WHERE pallet_id=%s', (identity,))
        assert cursor.fetchone()['total'] == 1
    finally:
        conn.close()


def test_two_concurrent_targets_cannot_move_same_pallet(registry_stock):
    def move(destination):
        conn = get_db_connection()
        try:
            WarehouseRegistry.move(conn, sscc=registry_stock, source='MS01', destination=destination, operation_key=uuid.uuid4().hex, operator='pytest')
            return True
        except ValueError:
            return False
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(move, ['OSIP', 'MP01'])) == [False, True]


def test_history_failure_rolls_back_stock(registry_stock):
    conn = get_db_connection()
    original = conn.cursor(dictionary=True)
    wrapper = MagicMock(wraps=original)
    def execute(sql, params=None):
        if 'INSERT INTO warehouse_events' in sql:
            raise RuntimeError('History failure')
        return original.execute(sql, params)
    wrapper.execute.side_effect = execute
    proxy = MagicMock(wraps=conn)
    proxy.cursor.return_value = wrapper
    try:
        with pytest.raises(RuntimeError, match='History failure'):
            WarehouseRegistry.move(proxy, sscc=registry_stock, source='MS01', destination='OSIP', operation_key=uuid.uuid4().hex, operator='pytest')
        original.execute('SELECT location,version FROM warehouse_pallets WHERE sscc=%s', (registry_stock,))
        assert original.fetchone() == {'location': 'MS01', 'version': 0}
    finally:
        conn.close()
