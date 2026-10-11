"""Read-only deployment checks. Never print credentials or contact integrations."""
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def inspect_environment(environ=None):
    env = os.environ if environ is None else environ
    results = []

    def flag(name, default=False):
        return str(env.get(name, str(default))).strip().lower() in {'true', '1', 'yes', 'on'}

    def configured(name, minimum=1):
        value = str(env.get(name, '')).strip()
        return len(value) >= minimum and not any(
            marker in value.upper() for marker in ('CHANGE_THIS', 'CHANGE-ME', 'REPLACE_WITH', 'YOUR-SECRET'))

    def check(name, passed, instruction):
        results.append({'check': name, 'passed': bool(passed), 'instruction': instruction})

    production = str(env.get('FLASK_ENV', env.get('ENV', ''))).lower() == 'production'
    check('production_mode', production, 'Set FLASK_ENV=production on the deployment.')
    check('session_cookie_https', flag('SESSION_COOKIE_SECURE', production),
          'Production session cookies must require HTTPS.')
    check('https_transport', flag('USE_SSL') or flag('TRUST_PROXY_HEADERS'),
          'Configure HTTPS or a network-restricted trusted HTTPS proxy; verify its live certificate separately.')
    if flag('USE_SSL'):
        try:
            from scripts.tls_security import validate_tls_files
            validate_tls_files(env.get('TLS_CERT_FILE', ''), env.get('TLS_KEY_FILE', ''))
            valid_tls = True
        except (OSError, ValueError, TypeError):
            valid_tls = False
        check('tls_certificate_and_key', valid_tls,
              'Mount a valid matching certificate and new private key; keys exposed in Git are blocked.')
    hosts = [host.strip() for host in str(env.get('TRUSTED_HOSTS', '')).split(',') if host.strip()]
    check('trusted_hosts', hosts and all('*' not in host and 'example.' not in host for host in hosts),
          'Set TRUSTED_HOSTS to the actual public application hostnames.')
    check('session_key', configured('SECRET_KEY', 32), 'Inject a unique random SECRET_KEY of at least 32 characters.')
    try:
        valid_key = len(base64.urlsafe_b64decode(str(env.get('ENCRYPTION_KEY', '')).encode())) == 32
    except (ValueError, TypeError):
        valid_key = False
    check('encryption_key', valid_key and env.get('SECRET_KEY') != env.get('ENCRYPTION_KEY'),
          'Inject a separate, valid Fernet ENCRYPTION_KEY.')
    check('database_tls', not flag('DB_SSL_DISABLED'), 'Keep DB_SSL_DISABLED=false.')
    ca_path = str(env.get('DB_SSL_CA', '')).strip()
    check('database_certificate', ca_path and Path(ca_path).is_file(),
          'Mount the trusted MySQL CA and set DB_SSL_CA; DB_HOST must match the certificate.')
    check('database_account', configured('DB_USER') and str(env.get('DB_USER')).lower() != 'root'
          and configured('DB_PASSWORD', 12), 'Use a dedicated database account with a strong injected password.')
    check('debug_disabled', not flag('FLASK_DEBUG') and not flag('ENABLE_DEBUG_ROUTES'), 'Disable production debug modes.')
    check('smtp_encrypted', not flag('SMTP_ALLOW_PLAINTEXT'), 'Do not enable plaintext SMTP.')
    check('smtp_private_scope', not flag('SMTP_ALLOW_PRIVATE_HOSTS'),
          'Allow individual internal mail servers explicitly, rather than all private addresses.')
    check('print_bridge_token', configured('PRINTER_BRIDGE_TOKEN', 32), 'Inject a long random print bridge token.')
    try:
        bridge = urlsplit(str(env.get('PRINTER_BRIDGE_URL', '')))
        safe_bridge = bridge.scheme == 'https' or (bridge.scheme == 'http'
                      and bridge.hostname in {'localhost', '127.0.0.1', '::1'})
    except ValueError:
        safe_bridge = False
    check('print_bridge_transport', safe_bridge,
          'Use verified HTTPS for a remote print bridge; HTTP is allowed only on loopback.')
    return results


def main():
    checks = inspect_environment()
    print(json.dumps({'passed': all(check['passed'] for check in checks), 'checks': checks}, indent=2))
    return 0 if all(check['passed'] for check in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
