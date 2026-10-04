# cspell:words sscc
"""One-time consolidation of the two finished-goods stock tables.

SSCC is the physical identity.  Numeric IDs from the old tables are retained
only as historical references in the mapping table; they never decide which
stock record wins.
"""
import json
from collections import defaultdict
from decimal import Decimal


class FinishedGoodsConsolidation:
    TABLES = ('magazyn_palety', 'magazyn_palety_agro')
    RECEIPT_ACTIONS = {'PRZYJECIE_WG', 'PRZYJECIE', 'PRZESUNIECIE', 'TRANSFER_RECEIVE', 'OSIP_RECEIVE'}

    @classmethod
    def plan(cls, cursor):
        cursor.execute("SELECT TABLE_NAME AS name,TABLE_TYPE AS type FROM information_schema.tables WHERE TABLE_SCHEMA=DATABASE()")
        tables = {r['name']: r['type'] for r in cursor.fetchall()}
        if tables.get('magazyn_palety') != 'BASE TABLE' or tables.get('magazyn_palety_agro') != 'BASE TABLE':
            raise ValueError('Scalanie wymaga dwóch niezmienionych tabel źródłowych.')
        cursor.execute('SHOW COLUMNS FROM magazyn_palety')
        columns = [r['Field'] for r in cursor.fetchall()]
        copies, history, production = defaultdict(list), defaultdict(list), defaultdict(list)
        for table in cls.TABLES:
            cursor.execute(f'SELECT * FROM {table} ORDER BY id')
            for row in cursor.fetchall():
                sscc = str(row.get('nr_palety') or '').strip().upper()
                if not sscc:
                    raise ValueError(f'Brak SSCC w {table}/{row["id"]}; scalanie zatrzymane.')
                copies[sscc].append(dict(table=table, row=row))
        cursor.execute('SELECT * FROM palety_historia ORDER BY data_ruchu,id')
        for row in cursor.fetchall():
            history[str(row.get('nr_palety') or '').strip().upper()].append(row)
        for table, line in (('palety_agro', 'AGRO'), ('palety_workowanie', 'PSD')):
            if table in tables:
                cursor.execute(f'SELECT * FROM {table}')
                for row in cursor.fetchall():
                    row['_line'] = line
                    production[str(row.get('nr_palety') or '').strip().upper()].append(row)
        records = [cls._resolve(sscc, entries, history[sscc], production[sscc])
                   for sscc, entries in sorted(copies.items())]
        return dict(columns=columns, records=records,
                    source_rows=sum(len(v) for v in copies.values()))

    @classmethod
    def _resolve(cls, sscc, copies, history, production):
        quantities = [Decimal(str(c['row'].get('waga_netto') or 0)) for c in copies]
        active = [c for c, q in zip(copies, quantities) if q > 0]
        reasons = []
        if any(q < 0 or not q.is_finite() for q in quantities):
            reasons.append('invalid_quantity')
        if len({q for q in quantities if q > 0}) > 1:
            reasons.append('different_quantity')
        locations = {str(c['row'].get('lokalizacja') or '').strip().upper() for c in active} - {''}
        if len(locations) > 1:
            reasons.append('different_location')
        lines = {str(c['row'].get('linia') or ('AGRO' if c['table'].endswith('_agro') else 'PSD')).upper()
                 for c in active}
        latest = next((h for h in reversed(history)
                       if h.get('akcja') in cls.RECEIPT_ACTIONS and h.get('lokalizacja_docelowa')), None)
        # A confirmed receipt matches SSCC, linked production row, date, weight and line.
        confirmed = []
        for copy in active:
            row = copy['row']
            for prod in production:
                if (prod.get('status') in ('przyjeta', 'w_magazynie')
                        and prod.get('data_potwierdzenia')
                        and row.get('paleta_workowanie_id') == prod.get('id')
                        and str(row.get('linia') or '').upper() == prod['_line']
                        and row.get('data_potwierdzenia') == prod.get('data_potwierdzenia')
                        and Decimal(str(row.get('waga_netto') or 0))
                        == Decimal(str(prod.get('waga_potwierdzona') or prod.get('waga') or 0))):
                    confirmed.append(copy)
        if len(active) > 1 and not reasons:
            if confirmed:
                target = str(confirmed[0]['row'].get('lokalizacja') or '').strip().upper()
                if target and all(str(c['row'].get('lokalizacja') or '').strip().upper() == target for c in active):
                    active = confirmed
                else:
                    reasons.append('receipt_location_not_proven')
            elif latest and str(latest.get('lokalizacja_docelowa')).strip().upper() in locations:
                active = [c for c in active if str(c['row'].get('lokalizacja') or '').strip().upper()
                          == str(latest['lokalizacja_docelowa']).strip().upper()]
            elif len(locations) != 1:
                reasons.append('unconfirmed_location')
            elif len(lines) > 1:
                reasons.append('unconfirmed_line')
        winner = (active or copies)[0]
        # Prefer an existing main-table ID when the stock facts are equal.  This
        # protects historic records that still display the old numeric ID.
        main = next((c for c in active if c['table'] == 'magazyn_palety'), None)
        if main and not reasons:
            winner = main
        row = dict(winner['row'])
        row['nr_palety'] = sscc
        row['linia'] = str(row.get('linia') or ('AGRO' if winner['table'].endswith('_agro') else 'PSD')).upper()
        if reasons:
            # No guessed quantity may become available stock.
            row.update(waga_netto=0, is_blocked=1, lokalizacja='KOREKTA_SSCC')
        return dict(sscc=sscc, row=row, copies=copies, reasons=sorted(set(reasons)))

    @classmethod
    def create_candidate(cls, cursor, plan):
        cursor.execute('CREATE TABLE unified_magazyn_palety LIKE magazyn_palety')
        cursor.execute('ALTER TABLE unified_magazyn_palety MODIFY id BIGINT NOT NULL AUTO_INCREMENT')
        cursor.execute('ALTER TABLE unified_magazyn_palety ADD UNIQUE KEY unified_sscc (nr_palety)')
        cursor.execute('''CREATE TABLE unified_magazyn_palety_sources (
            source_table VARCHAR(50) NOT NULL, source_id BIGINT NOT NULL,
            canonical_id BIGINT NOT NULL, sscc VARCHAR(100) NOT NULL,
            snapshot JSON NOT NULL, PRIMARY KEY(source_table,source_id), KEY source_sscc(sscc)
        ) ENGINE=InnoDB''')
        cursor.execute('''CREATE TABLE unified_magazyn_palety_conflicts (
            sscc VARCHAR(100) PRIMARY KEY, reasons JSON NOT NULL, snapshot JSON NOT NULL,
            resolved_at DATETIME NULL
        ) ENGINE=InnoDB''')
        used = set()
        next_id = max((c['row']['id'] for record in plan['records'] for c in record['copies']), default=0) + 1
        for record in plan['records']:
            row = {key: value for key, value in record['row'].items() if key in plan['columns'] and key != 'id'}
            proposed = record['row']['id'] if record['row'].get('id') not in used else next_id
            if proposed == next_id:
                next_id += 1
            used.add(proposed)
            row['id'] = proposed
            keys = list(row)
            cursor.execute(f"INSERT INTO unified_magazyn_palety ({','.join('`'+k+'`' for k in keys)}) VALUES ({','.join(['%s']*len(keys))})", tuple(row[k] for k in keys))
            for copy in record['copies']:
                cursor.execute('INSERT INTO unified_magazyn_palety_sources VALUES(%s,%s,%s,%s,%s)',
                               (copy['table'], copy['row']['id'], proposed, record['sscc'],
                                json.dumps(copy['row'], default=str)))
            if record['reasons']:
                cursor.execute('INSERT INTO unified_magazyn_palety_conflicts(sscc,reasons,snapshot) VALUES(%s,%s,%s)',
                               (record['sscc'], json.dumps(record['reasons']),
                                json.dumps(record['copies'], default=str)))
        cursor.execute('SELECT COUNT(*) AS total,COUNT(DISTINCT nr_palety) AS unique_count FROM unified_magazyn_palety')
        count = cursor.fetchone()
        if count['total'] != len(plan['records']) or count['unique_count'] != count['total']:
            raise ValueError('Kandydat nie ma dokładnie jednej palety na SSCC.')
        cursor.execute('SELECT COUNT(*) AS total FROM unified_magazyn_palety_sources')
        if cursor.fetchone()['total'] != plan['source_rows']:
            raise ValueError('Kandydat nie zachował wszystkich rekordów źródłowych.')

    @classmethod
    def switch(cls, connection, plan):
        """The caller must back up the complete local schema before this call."""
        cursor = connection.cursor(dictionary=True)
        cls.create_candidate(cursor, plan)
        connection.commit()
        cursor.execute('''RENAME TABLE magazyn_palety TO legacy_magazyn_palety,
            magazyn_palety_agro TO legacy_magazyn_palety_agro,
            unified_magazyn_palety TO magazyn_palety''')
        cursor.execute("CREATE VIEW magazyn_palety_agro AS SELECT * FROM magazyn_palety WHERE UPPER(linia)='AGRO'")
        # History is repaired by SSCC, never by the previously duplicated id.
        cursor.execute('''UPDATE palety_historia h JOIN magazyn_palety p
            ON UPPER(TRIM(h.nr_palety))=UPPER(TRIM(p.nr_palety))
            SET h.paleta_id=p.id WHERE h.nr_palety IS NOT NULL AND h.nr_palety<>'' ''')
        connection.commit()
        cursor.execute('SELECT COUNT(*) AS count FROM unified_magazyn_palety_conflicts')
        return dict(pallets=len(plan['records']), conflicts=cursor.fetchone()['count'])
