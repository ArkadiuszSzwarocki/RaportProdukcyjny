#!/usr/bin/env python3
"""
Diagnostyka mostka i drukarki dla RaportProdukcyjny
Uruchom:
  python scripts/diagnose_printer.py --printer-ip 192.168.1.160 --bridge-url http://127.0.0.1:3001 --tail 200 --db-check

Skrypt wykona:
 - test TCP na porcie 9100 do drukarki
 - POST do mostka /drukuj-zpl z prostym ZPL
 - wypisze ostatnie N linii z logs/printer_server_start.log i logs/app.log
 - opcjonalnie spróbuje połączyć się z DB i wypisać zawartość tabeli `drukarki` (jeśli dostępne dane w .env i pakiet mysql-connector-python)
"""
import os
import sys
import argparse
import socket
import json
import time
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin

try:
    import mysql.connector as mysql
except Exception:
    mysql = None


def test_tcp(ip, port=9100, timeout=3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        start = time.time()
        res = s.connect_ex((ip, port))
        elapsed = time.time() - start
        s.close()
        ok = (res == 0)
        return {'ok': ok, 'code': res, 'elapsed_s': round(elapsed, 3)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def post_bridge(bridge_url, printer_ip, timeout=5):
    endpoint = bridge_url.rstrip('/') + '/drukuj-zpl'
    payload = json.dumps({
        'drukarka': 'Diagnostyka',
        'ip': printer_ip,
        'dane': '^XA^FO50,50^A0N,30,30^FDTEST^FS^XZ'
    }).encode('utf-8')
    req = urlrequest.Request(endpoint, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            return {'status': resp.getcode(), 'body': body}
    except HTTPError as he:
        return {'status': he.code, 'error': he.read().decode('utf-8', errors='replace')}
    except URLError as ue:
        return {'error': str(ue)}
    except Exception as e:
        return {'error': str(e)}


def tail_file(path, lines=200):
    if not os.path.exists(path):
        return [f'<missing: {path}>']
    with open(path, 'rb') as f:
        avg_line = 200
        to_read = lines * avg_line
        try:
            f.seek(-to_read, os.SEEK_END)
        except Exception:
            f.seek(0)
        data = f.read().decode('utf-8', errors='replace')
    arr = data.splitlines()
    return arr[-lines:]


def query_drukarki_from_env():
    if not mysql:
        return {'error': 'mysql-connector-python not installed'}
    # read DB config from environment or .env
    from dotenv import load_dotenv
    load_dotenv(override=False)
    cfg = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 3307)),
        'database': os.getenv('DB_NAME', 'biblioteka'),
        'user': os.getenv('DB_USER', 'biblioteka'),
        'password': os.getenv('DB_PASSWORD', ''),
        'connect_timeout': 5,
    }
    try:
        conn = mysql.connect(**cfg)
    except Exception as e:
        return {'error': f'connect failed: {e}', 'cfg': cfg}
    try:
        cur = conn.cursor()
        cur.execute('SELECT id, nazwa, ip, lokalizacja, aktywna FROM drukarki ORDER BY id')
        rows = cur.fetchall()
        return {'rows': rows}
    except Exception as e:
        return {'error': f'query failed: {e}'}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--printer-ip', default=os.getenv('DIAG_PRINTER_IP', '192.168.1.160'))
    p.add_argument('--bridge-url', default=os.getenv('PRINTER_BRIDGE_URL', 'http://127.0.0.1:3001'))
    p.add_argument('--tail', type=int, default=200)
    p.add_argument('--db-check', action='store_true')
    args = p.parse_args()

    out = {'printer_ip': args.printer_ip, 'bridge_url': args.bridge_url}

    print('\n== TCP test to printer ==')
    tcp = test_tcp(args.printer_ip)
    print(json.dumps(tcp, ensure_ascii=False, indent=2))
    out['tcp'] = tcp

    print('\n== POST to bridge (/drukuj-zpl) ==')
    post = post_bridge(args.bridge_url, args.printer_ip)
    print(json.dumps(post, ensure_ascii=False, indent=2))
    out['post'] = post

    print(f"\n== Tail {args.tail} lines: logs/printer_server_start.log ==")
    tail1 = tail_file(os.path.join('logs', 'printer_server_start.log'), args.tail)
    for line in tail1:
        print(line)
    out['tail_printer_server'] = tail1[-args.tail:]

    print(f"\n== Tail {args.tail} lines: logs/app.log (if exists) ==")
    applog = None
    candidate = None
    # try to find most recent app.log.*
    logs_dir = 'logs'
    if os.path.isdir(logs_dir):
        files = sorted([os.path.join(logs_dir, f) for f in os.listdir(logs_dir) if f.startswith('app.log')])
        if files:
            candidate = files[-1]
    if candidate:
        tail2 = tail_file(candidate, args.tail)
        for line in tail2:
            print(line)
        out['tail_app_log'] = tail2[-args.tail:]
    else:
        print('<no app.log found>')
        out['tail_app_log'] = []

    if args.db_check:
        print('\n== DB: SELECT FROM drukarki ==')
        dbres = query_drukarki_from_env()
        print(json.dumps(dbres, default=str, ensure_ascii=False, indent=2))
        out['db'] = dbres

    # dump summary to file
    summary_path = os.path.join('logs', f'diagnostic_printer_summary_{int(time.time())}.json')
    try:
        with open(summary_path, 'w', encoding='utf-8') as wf:
            json.dump(out, wf, ensure_ascii=False, indent=2)
        print(f'\nSummary saved to: {summary_path}')
    except Exception as e:
        print('Failed to write summary:', e)


if __name__ == '__main__':
    main()
