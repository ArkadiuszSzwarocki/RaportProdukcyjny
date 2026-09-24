"""
Production Gunicorn configuration for RaportProdukcyjny.
"""
import os

bind = f"{os.environ.get('HOST', '0.0.0.0')}:{os.environ.get('PORT', '8082')}"
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get('LOG_LEVEL', 'info').lower()

worker_class = "gthread"

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Optional SSL configuration
use_ssl = os.environ.get('USE_SSL', 'false').lower() == 'true'
cert_path = os.path.join("certs", "cert.pem")
key_path = os.path.join("certs", "key.pem")

if use_ssl and os.path.exists(cert_path) and os.path.exists(key_path):
    keyfile = key_path
    certfile = cert_path
