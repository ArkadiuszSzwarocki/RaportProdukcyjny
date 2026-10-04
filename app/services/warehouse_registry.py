# cspell:words sscc lastrowid
"""Isolated migration candidate: one physical pallet and one atomic movement writer.

No automatic migrations or application switch. Call only on a disposable copy.
"""
import hashlib
import json
from decimal import Decimal


class WarehouseRegistry:
    SOURCES = {
        'magazyn_surowce': ('raw', 'stan_magazynowy', 'nazwa'),
        'magazyn_agro_surowce': ('raw', 'stan_magazynowy', 'nazwa'),
        'magazyn_opakowania': ('packaging', 'stan_magazynowy', 'nazwa'),
        'magazyn_agro_opakowania': ('packaging', 'stan_magazynowy', 'nazwa'),
        'magazyn_dodatki': ('additive', 'stan_magazynowy', 'nazwa'),
        'magazyn_palety': ('finished', 'waga_netto', 'produkt'),
        'magazyn_palety_agro': ('finished', 'waga_netto', 'produkt'),
    }

    @staticmethod
    def assert_copy(cursor):
        cursor.execute('SELECT DATABASE() AS name')
        if not str(cursor.fetchone()['name']).startswith(('rp_pr17_unified_', 'rp_pr17_pytest_')):
            raise ValueError('Migracja jest dozwolona wyłącznie na osobnej kopii testowej.')

    @classmethod
    def create_schema(cls, cursor):
        cls.assert_copy(cursor)
        cursor.execute('''CREATE TABLE IF NOT EXISTS warehouse_pallets (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            sscc VARCHAR(100) NOT NULL UNIQUE,
            kind VARCHAR(20) NOT NULL, product_name VARCHAR(255) NOT NULL,
            quantity DECIMAL(18,6) NOT NULL, unit VARCHAR(10) NOT NULL,
            location VARCHAR(100) NOT NULL, hall VARCHAR(20) NOT NULL,
            blocked BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSON NOT NULL, source_table VARCHAR(100) NOT NULL,
            source_id BIGINT NOT NULL, version BIGINT NOT NULL DEFAULT 0
        ) ENGINE=InnoDB''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS warehouse_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            pallet_id BIGINT NOT NULL, operation_key VARCHAR(100) NOT NULL UNIQUE,
            action VARCHAR(50) NOT NULL, source_location VARCHAR(100) NOT NULL,
            target_location VARCHAR(100) NOT NULL,
            quantity_before DECIMAL(18,6) NULL, quantity_after DECIMAL(18,6) NULL,
            operator VARCHAR(100) NOT NULL, metadata JSON NOT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            FOREIGN KEY (pallet_id) REFERENCES warehouse_pallets(id)
        ) ENGINE=InnoDB''')

    @classmethod
    def inventory(cls, cursor):
        cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'")
        tables = {row['name'] for row in cursor.fetchall()}
        records, problems, seen = [], [], {}
        for table, (kind, quantity_column, name_column) in cls.SOURCES.items():
            if table not in tables:
                continue  # A view is another screen of the same stock, never another pallet.
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY id')
            for row in cursor.fetchall():
                code = str(row.get('nr_palety') or '').strip().upper()
                quantity = Decimal(str(row.get(quantity_column) or 0))
                source = {'table': table, 'id': row['id']}
                if not quantity.is_finite() or quantity < 0:
                    problems.append(dict(reason='invalid_quantity', **source))
                    continue
                if not code:
                    if quantity:
                        problems.append(dict(reason='missing_sscc', **source))
                    continue
                if code in seen:
                    problems.append(dict(reason='duplicate_sscc', sscc=code, sources=[seen[code], source]))
                    continue  # Never sum quantities of apparent copies.
                seen[code] = source
                record = dict(sscc=code, kind=kind, product_name=str(row.get(name_column) or ''),
                              quantity=str(quantity), unit='szt' if kind == 'packaging' else 'kg',
                              location=str(row.get('lokalizacja') or '').strip().upper(),
                              hall=str(row.get('linia') or ('AGRO' if 'agro' in table else '')).upper(),
                              blocked=bool(row.get('is_blocked')), source_table=table, source_id=row['id'],
                              metadata=json.dumps(row, default=str, ensure_ascii=False))
                records.append(record)
        return records, problems

    @staticmethod
    def fingerprint(records):
        content = json.dumps(sorted(records, key=lambda row: row['sscc']), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

    @classmethod
    def migrate(cls, connection):
        cursor = connection.cursor(dictionary=True)
        cls.assert_copy(cursor)
        records, problems = cls.inventory(cursor)
        if problems:
            connection.rollback()
            return dict(ready=False, problems=problems, candidate_count=len(records))
        cursor.execute('SELECT COUNT(*) AS total FROM warehouse_pallets')
        if cursor.fetchone()['total']:
            raise ValueError('Rejestr nie jest pusty; istniejącej migracji nie nadpisujemy.')
        names = ('sscc', 'kind', 'product_name', 'quantity', 'unit', 'location', 'hall', 'blocked', 'metadata', 'source_table', 'source_id')
        try:
            for record in records:
                cursor.execute(f"INSERT INTO warehouse_pallets ({','.join(names)}) VALUES ({','.join(['%s'] * len(names))})",
                               tuple(record[name] for name in names))
            cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='palety_historia'")
            if cursor.fetchone():
                cursor.execute('SELECT * FROM palety_historia ORDER BY id')
                history = cursor.fetchall()
                for event in history:
                    code = str(event.get('nr_palety') or '').strip().upper()
                    if not code:
                        continue  # Ambiguous legacy history stays in the source snapshot.
                    cursor.execute('SELECT id,quantity FROM warehouse_pallets WHERE sscc=%s', (code,))
                    pallet = cursor.fetchone()
                    if not pallet:
                        continue
                    # Preserve original data; no reconstructed quantities are claimed as measurements.
                    cursor.execute('''INSERT INTO warehouse_events(pallet_id,operation_key,action,
                        source_location,target_location,quantity_before,quantity_after,operator,metadata,created_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP(6)))''',
                        (pallet['id'], f"legacy-history:{event['id']}", event.get('akcja') or 'LEGACY',
                         event.get('lokalizacja_zrodlowa') or '', event.get('lokalizacja_docelowa') or '',
                         event.get('quantity_before'), event.get('quantity_after'),
                         event.get('user_login') or '', json.dumps(event, default=str, ensure_ascii=False), event.get('data_ruchu')))
            reconciliation = cls.reconcile(cursor)
            if not reconciliation['equal']:
                connection.rollback()
                return dict(ready=False, reconciliation=reconciliation)
            connection.commit()
            return dict(ready=True, pallet_count=len(records), source_fingerprint=cls.fingerprint(records),
                        reconciliation=reconciliation)
        except Exception:
            connection.rollback()
            raise

    @classmethod
    def reconcile(cls, cursor):
        records, problems = cls.inventory(cursor)
        cursor.execute('SELECT * FROM warehouse_pallets ORDER BY sscc')
        actual = {row['sscc']: row for row in cursor.fetchall()}
        differences = []
        expected = {row['sscc']: row for row in records}
        for code in set(expected) | set(actual):
            source, target = expected.get(code), actual.get(code)
            if not source or not target:
                differences.append(dict(sscc=code, field='presence'))
                continue
            for field in ('kind', 'product_name', 'quantity', 'unit', 'location', 'hall', 'blocked'):
                left, right = source[field], target[field]
                equal = Decimal(str(left)) == Decimal(str(right)) if field == 'quantity' else left == right
                if not equal:
                    differences.append(dict(sscc=code, field=field))
        return dict(equal=not differences and not problems, differences=differences, problems=problems)

    @classmethod
    def move(cls, connection, *, sscc, source, destination, operation_key, operator):
        return cls.transition(connection, sscc=sscc, source=source, destination=destination,
                              operation_key=operation_key, operator=operator, action='MOVE')

    @classmethod
    def transition(cls, connection, *, sscc, source, destination, operation_key, operator,
                   action, quantity=None):
        """Candidate writer: caller supplies verified destination and existing authorization.

        Intentionally copy-only until reservations, rack rules and all adapters are migrated.
        """
        cursor = connection.cursor(dictionary=True)
        cls.assert_copy(cursor)
        code = str(sscc).strip().upper()
        source, destination = str(source).strip().upper(), str(destination).strip().upper()
        if action not in ('MOVE', 'RECEIVE', 'DISPATCH'):
            raise ValueError('Nieznana operacja magazynowa.')
        issued = Decimal(str(quantity)) if quantity is not None else None
        if action == 'DISPATCH' and (issued is None or not issued.is_finite() or issued <= 0):
            raise ValueError('Wydawana ilość musi być dodatnia.')
        if action != 'DISPATCH' and issued is not None:
            raise ValueError('Przesunięcie i odbiór nie zmieniają ilości palety.')
        if not code or not operation_key or not destination or (source == destination and action != 'DISPATCH'):
            raise ValueError('Niepoprawne dane ruchu palety.')
        try:
            cursor.execute('SELECT * FROM warehouse_pallets WHERE sscc=%s FOR UPDATE', (code,))
            pallet = cursor.fetchone()
            if not pallet:
                raise ValueError('Nie znaleziono palety o wskazanym SSCC.')
            cursor.execute('SELECT * FROM warehouse_events WHERE operation_key=%s', (operation_key,))
            event = cursor.fetchone()
            if event:
                same = (event['pallet_id'], event['action'], event['source_location'], event['target_location']) == (pallet['id'], action, source, destination)
                if action == 'DISPATCH':
                    same = same and event['quantity_before'] - event['quantity_after'] == issued
                if not same:
                    raise ValueError('Klucz operacji dotyczy innego ruchu.')
                connection.rollback()
                return pallet['id']
            if pallet['blocked'] or pallet['quantity'] <= 0 or pallet['location'] != source:
                raise ValueError('Stan palety zmienił się lub paleta jest zablokowana.')
            after = pallet['quantity'] - issued if action == 'DISPATCH' else pallet['quantity']
            if after < 0:
                raise ValueError('Brak wymaganej ilości palety do wydania.')
            cursor.execute('UPDATE warehouse_pallets SET location=%s,quantity=%s,version=version+1 WHERE sscc=%s', (destination, after, code))
            cursor.execute('''INSERT INTO warehouse_events(pallet_id,operation_key,action,source_location,
                target_location,quantity_before,quantity_after,operator,metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'{}')''',
                (pallet['id'], operation_key, action, source, destination, pallet['quantity'], after, operator))
            connection.commit()
            return pallet['id']
        except Exception:
            connection.rollback()
            raise
