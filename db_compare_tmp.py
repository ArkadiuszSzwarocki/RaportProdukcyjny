import os, json, hashlib
from dotenv import load_dotenv

load_dotenv(r'C:\Users\arkad\Documents\github\RaportProdukcyjny\.env', override=False)
import mysql.connector

base = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'connection_timeout': 12,
    'autocommit': True,
}
use_ssl = os.getenv('USE_SSL', 'false').lower() in ('1', 'true', 'yes', 'on')
base['ssl_disabled'] = not use_ssl

def get_db(name):
    cfg = dict(base, database=name)
    try:
        return mysql.connector.connect(**cfg)
    except Exception as e:
        msg = str(e)
        if 'secure connection' in msg.lower() or 'caching_sha2' in msg.lower():
            cfg['ssl_disabled'] = False
            return mysql.connector.connect(**cfg)
        raise

def rows(cur, q, p=()):
    cur.execute(q, p)
    return cur.fetchall()

def sig(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

names = ['biblioteka', 'biblioteka_testowa', 'biblioteka_test']
report = {}
for name in names:
    try:
        cn = get_db(name)
        cur = cn.cursor(dictionary=True)
        tables = rows(cur, 'SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.tables WHERE table_schema=%s ORDER BY TABLE_NAME', (name,))
        cols = rows(cur, 'SELECT TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,COLUMN_KEY FROM information_schema.columns WHERE table_schema=%s ORDER BY TABLE_NAME,ORDINAL_POSITION', (name,))
        idx = rows(cur, 'SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,COLLATION,SUB_PART,INDEX_TYPE FROM information_schema.statistics WHERE table_schema=%s ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX', (name,))
        rowmeta = rows(cur, 'SELECT TABLE_NAME,TABLE_ROWS,ENGINE FROM information_schema.tables WHERE table_schema=%s ORDER BY TABLE_NAME', (name,))
        report[name] = {'tables': tables, 'cols': cols, 'idx': idx, 'rowmeta': rowmeta}
        cur.close(); cn.close()
    except Exception as e:
        report[name] = {'error': type(e).__name__ + ': ' + str(e)}

for name in names:
    x = report[name]
    if 'error' in x:
        print(name + ' ERROR ' + x['error'])
    else:
        print(name + ' tables=' + str(len(x['tables'])) + ' columns=' + str(len(x['cols'])) + ' indexes=' + str(len(x['idx'])) + ' schema_sig=' + sig({'tables': x['tables'], 'cols': x['cols'], 'idx': x['idx']}))

if all('error' not in report[n] for n in names[:2]):
    a, b = report['biblioteka'], report['biblioteka_testowa']
    ta = {r['TABLE_NAME'] for r in a['tables']}; tb = {r['TABLE_NAME'] for r in b['tables']}
    print('missing_in_biblioteka_testowa=' + json.dumps(sorted(ta - tb), ensure_ascii=False))
    print('extra_in_biblioteka_testowa=' + json.dumps(sorted(tb - ta), ensure_ascii=False))

    def normcols(x):
        return {(r['TABLE_NAME'], r['COLUMN_NAME']): (r['ORDINAL_POSITION'], r['COLUMN_TYPE'], r['IS_NULLABLE'], str(r['COLUMN_DEFAULT']), r['EXTRA'], r['COLUMN_KEY']) for r in x}
    ca, cb = normcols(a['cols']), normcols(b['cols'])
    diffcols = sorted(set(ca) | set(cb))
    diffcols = [k for k in diffcols if ca.get(k) != cb.get(k)]
    print('differing_columns=' + json.dumps([{'table': k[0], 'column': k[1], 'biblioteka': ca.get(k), 'testowa': cb.get(k)} for k in diffcols], ensure_ascii=False, default=str))

    def normidx(x):
        return {(r['TABLE_NAME'], r['INDEX_NAME'], r['SEQ_IN_INDEX']): (r['NON_UNIQUE'], r['COLUMN_NAME'], r['COLLATION'], r['SUB_PART'], r['INDEX_TYPE']) for r in x}
    ia, ib = normidx(a['idx']), normidx(b['idx'])
    di = sorted(set(ia) | set(ib))
    di = [k for k in di if ia.get(k) != ib.get(k)]
    print('differing_indexes=' + json.dumps([{'key': k, 'biblioteka': ia.get(k), 'testowa': ib.get(k)} for k in di], ensure_ascii=False, default=str))

    ra = {r['TABLE_NAME']: r['TABLE_ROWS'] for r in a['rowmeta']}; rb = {r['TABLE_NAME']: r['TABLE_ROWS'] for r in b['rowmeta']}
    rowdiff = [(t, ra.get(t), rb.get(t)) for t in sorted(ta & tb) if ra.get(t) != rb.get(t)]
    print('rowmeta_differences_count=' + str(len(rowdiff)))
    print('rowmeta_differences=' + json.dumps(rowdiff[:100], ensure_ascii=False, default=str))
