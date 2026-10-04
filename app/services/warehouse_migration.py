# cspell:words sscc lastrowid
"""Stage verified SSCC groups on a copy; retain unresolved stock and all provenance."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal

from app.services.warehouse_registry import WarehouseRegistry


class WarehouseMigration:
    MOVEMENTS = {'PRZESUNIECIE', 'PRZYJECIE', 'TRANSFER_RECEIVE', 'OSIP_RECEIVE', 'TRANSFER_ACCEPT_ITEM'}

    @classmethod
    def plan(cls, cursor):
        WarehouseRegistry.assert_copy(cursor)
        cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'")
        tables = {row['name'] for row in cursor.fetchall()}
        groups = defaultdict(list)
        snapshot = []
        for table, (kind, quantity, product) in WarehouseRegistry.SOURCES.items():
            if table not in tables:
                continue
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY id')
            for row in cursor.fetchall():
                code = str(row.get('nr_palety') or '').strip().upper()
                entry = dict(table=table, row=row, kind=kind, quantity=quantity, product=product)
                snapshot.append(entry)
                groups[code or f"MISSING:{table}:{row['id']}"].append(entry)
        history = []
        if 'palety_historia' in tables:
            cursor.execute('SELECT * FROM palety_historia ORDER BY data_ruchu,id')
            history = cursor.fetchall()
        by_code = defaultdict(list)
        for event in history:
            by_code[str(event.get('nr_palety') or '').strip().upper()].append(event)
        records, issues = [], []
        for code, copies in groups.items():
            reasons = []
            quantities = [Decimal(str(entry['row'].get(entry['quantity']) or 0)) for entry in copies]
            if any(not value.is_finite() or value < 0 for value in quantities):
                reasons.append('invalid_quantity')
            active = [entry for entry, value in zip(copies, quantities) if value.is_finite() and value > 0]
            if code.startswith('MISSING:'):
                issues.append(dict(key=code, reasons=['missing_sscc'], copies=copies))
                continue
            candidates = active or copies
            # Old zero-quantity rows are historical evidence, not available stock.
            if len(active) > 1:
                signatures = {(
                    entry['kind'], Decimal(str(entry['row'].get(entry['quantity']))),
                    str(entry['row'].get(entry['product']) or '').strip(),
                    str(entry['row'].get('nr_partii') or '').strip(),
                    str(entry['row'].get('data_produkcji') or ''),
                    str(entry['row'].get('data_przydatnosci') or ''),
                ) for entry in active}
                if len(signatures) != 1:
                    reasons.append('different_stock_state')
                locations = {str(entry['row'].get('lokalizacja') or '').strip().upper() for entry in active}
                latest = next((event for event in reversed(by_code[code]) if event.get('lokalizacja_docelowa')), None)
                destination = str(latest.get('lokalizacja_docelowa') or '').strip().upper() if latest else ''
                if not latest or latest.get('akcja') not in cls.MOVEMENTS:
                    reasons.append('missing_confirmed_movement')
                if len(locations - {''}) > 1 or not destination or destination not in locations:
                    reasons.append('location_conflict')
                candidates = [entry for entry in active if str(entry['row'].get('lokalizacja') or '').strip().upper() == destination]
            if reasons:
                issues.append(dict(key=code, reasons=reasons, copies=copies))
                continue
            chosen = candidates[0]
            row = chosen['row']
            records.append(dict(
                sscc=code, kind=chosen['kind'], product_name=str(row.get(chosen['product']) or ''),
                quantity=str(Decimal(str(row.get(chosen['quantity']) or 0))),
                unit='szt' if chosen['kind'] == 'packaging' else 'kg',
                location=str(row.get('lokalizacja') or '').strip().upper(),
                hall=str(row.get('linia') or ('AGRO' if 'agro' in chosen['table'] else '')).upper(),
                blocked=any(bool(entry['row'].get('is_blocked')) for entry in copies),
                metadata=json.dumps(row, default=str, ensure_ascii=False),
                source_table=chosen['table'], source_id=row['id'], copies=copies,
            ))
        fingerprint = hashlib.sha256(json.dumps(dict(stock=snapshot, history=history), default=str,
                                                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return dict(records=records, issues=issues, history=history, fingerprint=fingerprint,
                    source_count=len(snapshot))

    @classmethod
    def stage(cls, connection, expected_fingerprint):
        cursor = connection.cursor(dictionary=True)
        WarehouseRegistry.assert_copy(cursor)
        cursor.execute('''CREATE TABLE IF NOT EXISTS warehouse_pallet_sources (
            source_table VARCHAR(100) NOT NULL, source_id BIGINT NOT NULL,
            pallet_id BIGINT NOT NULL, snapshot JSON NOT NULL,
            PRIMARY KEY(source_table,source_id),
            FOREIGN KEY(pallet_id) REFERENCES warehouse_pallets(id)) ENGINE=InnoDB''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS warehouse_migration_issues (
            issue_key VARCHAR(255) PRIMARY KEY, reasons JSON NOT NULL,
            snapshot JSON NOT NULL) ENGINE=InnoDB''')
        connection.commit()
        try:
            plan = cls.plan(cursor)
            if plan['fingerprint'] != expected_fingerprint:
                raise ValueError('Kopia zmieniła się od weryfikacji; przygotuj nowy plan.')
            for table in ('warehouse_pallets', 'warehouse_events', 'warehouse_pallet_sources', 'warehouse_migration_issues'):
                cursor.execute(f'SELECT COUNT(*) AS total FROM {table}')
                if cursor.fetchone()['total']:
                    raise ValueError('Próbna migracja wymaga pustego rejestru.')
            names = ('sscc','kind','product_name','quantity','unit','location','hall','blocked','metadata','source_table','source_id')
            identities = {}
            for record in plan['records']:
                cursor.execute(f"INSERT INTO warehouse_pallets ({','.join(names)}) VALUES ({','.join(['%s'] * len(names))})",
                               tuple(record[name] for name in names))
                identities[record['sscc']] = cursor.lastrowid
                for copy in record['copies']:
                    cursor.execute('INSERT INTO warehouse_pallet_sources(source_table,source_id,pallet_id,snapshot) VALUES(%s,%s,%s,%s)',
                                   (copy['table'],copy['row']['id'],identities[record['sscc']],json.dumps(copy,default=str,ensure_ascii=False)))
            for issue in plan['issues']:
                cursor.execute('INSERT INTO warehouse_migration_issues(issue_key,reasons,snapshot) VALUES(%s,%s,%s)',
                               (issue['key'],json.dumps(issue['reasons']),json.dumps(issue['copies'],default=str,ensure_ascii=False)))
            imported_history = 0
            for event in plan['history']:
                code = str(event.get('nr_palety') or '').strip().upper()
                if code not in identities:
                    continue
                cursor.execute('''INSERT INTO warehouse_events(pallet_id,operation_key,action,source_location,
                    target_location,quantity_before,quantity_after,operator,metadata,created_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP(6)))''',
                    (identities[code],f"legacy-history:{event['id']}",event.get('akcja') or 'LEGACY',
                     event.get('lokalizacja_zrodlowa') or '',event.get('lokalizacja_docelowa') or '',
                     event.get('quantity_before'),event.get('quantity_after'),event.get('user_login') or '',
                     json.dumps(event,default=str,ensure_ascii=False),event.get('data_ruchu')))
                imported_history += 1
            cursor.execute('SELECT * FROM warehouse_pallets')
            actual = {row['sscc']: row for row in cursor.fetchall()}
            for record in plan['records']:
                for field in ('kind','product_name','quantity','unit','location','hall','blocked'):
                    expected = Decimal(record[field]) if field == 'quantity' else record[field]
                    if actual[record['sscc']][field] != expected:
                        raise ValueError(f"Niezgodność migracji {record['sscc']}: {field}")
            accounted = sum(len(record['copies']) for record in plan['records']) + sum(len(issue['copies']) for issue in plan['issues'])
            if accounted != plan['source_count']:
                raise ValueError('Nie wszystkie zapisy źródłowe zostały zachowane.')
            connection.commit()
            return dict(staged=True, ready=not plan['issues'], pallets=len(actual),
                        unresolved=len(plan['issues']), source_records=accounted,
                        imported_history=imported_history, retained_legacy_history=len(plan['history'])-imported_history,
                        fingerprint=plan['fingerprint'], reconciliation_equal=True)
        except Exception:
            connection.rollback()
            raise
