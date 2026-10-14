#!/usr/bin/env python3
"""Diagnostics for an explicitly configured printer and authenticated print bridge.

Example:
  python scripts/diagnose_printer.py --printer-ip 10.0.0.10 --bridge-url http://127.0.0.1:3001 --tail 200 --db-check
"""

import argparse
import ipaddress
import json
import os
import socket
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

try:
    import mysql.connector as mysql
except Exception:
    mysql = None


def _validate_private_ip(value):
    address = ipaddress.ip_address(str(value or '').strip())
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise ValueError('Diagnostyka drukarki jest ograniczona do prywatnych/lokalnych adresów IP.')
    return str(address)


def test_tcp(ip, port=9100, timeout=3):
    target = _validate_private_ip(ip)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            start = time.time()
            result = sock.connect_ex((target, int(port)))
            elapsed = time.time() - start
        return {'ok': result == 0, 'code': result, 'elapsed_s': round(elapsed, 3)}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


def post_bridge(bridge_url, printer_ip, token, timeout=5):
    endpoint = bridge_url.rstrip('/') + '/drukuj-zpl'
    payload = json.dumps({
        'drukarka': os.getenv('PRINTER_NAME', 'Diagnostyka'),
        'ip': _validate_private_ip(printer_ip),
        'dane': '^XA^FO50,50^A0N,30,30^FDTEST^FS^XZ',
    }).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urlrequest.Request(endpoint, data=payload, headers=headers)
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            return {
                'status': response.getcode(),
                'body': response.read().decode('utf-8', errors='replace'),
            }
    except HTTPError as exc:
        return {'status': exc.code, 'error': exc.read().decode('utf-8', errors='replace')}
    except URLError as exc:
        return {'error': str(exc)}
    except Exception as exc:
        return {'error': str(exc)}


def tail_file(path, lines=200):
    if not os.path.exists(path):
        return [f'<missing: {path}>']
    with open(path, 'rb') as handle:
        try:
            handle.seek(-(lines * 200), os.SEEK_END)
        except OSError:
            handle.seek(0)
        data = handle.read().decode('utf-8', errors='replace')
    return data.splitlines()[-lines:]


def query_drukarki_from_env():
    if not mysql:
        return {'error': 'mysql-connector-python not installed'}
    from dotenv import load_dotenv
    load_dotenv(override=False)
    cfg = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 3306)),
        'database': os.getenv('DB_NAME', 'biblioteka'),
        'user': os.getenv('DB_USER', 'biblioteka'),
        'password': os.getenv('DB_PASSWORD', ''),
        'connect_timeout': 5,
    }
    try:
        conn = mysql.connect(**cfg)
    except Exception as exc:
        safe_cfg = {**cfg, 'password': '<redacted>'}
        return {'error': f'connect failed: {exc}', 'cfg': safe_cfg}
    try:
        cur = conn.cursor()
        cur.execute('SELECT id, nazwa, ip, lokalizacja, aktywna FROM drukarki ORDER BY id')
        return {'rows': cur.fetchall()}
    except Exception as exc:
        return {'error': f'query failed: {exc}'}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--printer-ip', default=os.getenv('DIAG_PRINTER_IP'))
    parser.add_argument('--printer-port', type=int, default=int(os.getenv('PRINTER_PORT', 9100)))
    parser.add_argument('--bridge-url', default=os.getenv('PRINTER_BRIDGE_URL', 'http://127.0.0.1:3001'))
    parser.add_argument('--bridge-token', default=os.getenv('PRINTER_BRIDGE_TOKEN', ''))
    parser.add_argument('--tail', type=int, default=200)
    parser.add_argument('--db-check', action='store_true')
    args = parser.parse_args()

    if not args.printer_ip:
        parser.error('--printer-ip or DIAG_PRINTER_IP is required')
    target_ip = _validate_private_ip(args.printer_ip)
    out = {'printer_ip': target_ip, 'bridge_url': args.bridge_url}

    print('\n== TCP test to printer ==')
    tcp = test_tcp(target_ip, args.printer_port)
    print(json.dumps(tcp, ensure_ascii=False, indent=2))
    out['tcp'] = tcp

    print('\n== POST to authenticated bridge (/drukuj-zpl) ==')
    post = post_bridge(args.bridge_url, target_ip, args.bridge_token)
    print(json.dumps(post, ensure_ascii=False, indent=2))
    out['post'] = post

    print(f'\n== Tail {args.tail} lines: logs/printer_server_start.log ==')
    tail1 = tail_file(os.path.join('logs', 'printer_server_start.log'), args.tail)
    for line in tail1:
        print(line)
    out['tail_printer_server'] = tail1

    print(f'\n== Tail {args.tail} lines: newest logs/app.log* ==')
    logs_dir = 'logs'
    candidates = []
    if os.path.isdir(logs_dir):
        candidates = sorted(
            os.path.join(logs_dir, name)
            for name in os.listdir(logs_dir)
            if name.startswith('app.log')
        )
    if candidates:
        tail2 = tail_file(candidates[-1], args.tail)
        for line in tail2:
            print(line)
        out['tail_app_log'] = tail2
    else:
        print('<no app.log found>')
        out['tail_app_log'] = []

    if args.db_check:
        print('\n== DB: SELECT FROM drukarki ==')
        db_result = query_drukarki_from_env()
        print(json.dumps(db_result, default=str, ensure_ascii=False, indent=2))
        out['db'] = db_result

    os.makedirs('logs', exist_ok=True)
    summary_path = os.path.join('logs', f'diagnostic_printer_summary_{int(time.time())}.json')
    with open(summary_path, 'w', encoding='utf-8') as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    print(f'\nSummary saved to: {summary_path}')


if __name__ == '__main__':
    main()
