"""Environment-backed application configuration."""

import os

from dotenv import load_dotenv


# Never override values injected by CI, containers or a secret manager.
load_dotenv(override=False)

SECRET_KEY = os.getenv('SECRET_KEY')
APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:8082').rstrip('/')
WATCHDOG_URL = os.getenv('WATCHDOG_URL') or None

# Database transport is independent from web-server TLS.  MySQL TLS is enabled
# by default; set DB_SSL_DISABLED=true only for a deliberately isolated local
# development environment that cannot provide TLS.
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'user': os.getenv('DB_USER', 'biblioteka'),
    'password': os.getenv('DB_PASSWORD', ''),
    'charset': os.getenv('DB_CHARSET', 'utf8mb4'),
    'connection_timeout': int(os.getenv('DB_CONNECTION_TIMEOUT', 20)),
    'ssl_disabled': os.getenv('DB_SSL_DISABLED', 'false').strip().lower() in ('1', 'true', 'yes'),
    'autocommit': False,
}

EMAIL_RECIPIENTS = os.getenv(
    'EMAIL_RECIPIENTS',
    'lider@example.com,szef@example.com,biuro@example.com',
).split(',')
EMAIL_RECIPIENTS = [email.strip() for email in EMAIL_RECIPIENTS if email.strip()]

MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False') == 'True'
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'Raport Produkcyjny <noreply@example.com>')

os.makedirs('raporty', exist_ok=True)

SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', 720))
BUFOR_LOOKBACK_DAYS = int(os.getenv('BUFOR_LOOKBACK_DAYS', 1))
BUFOR_LOOKAHEAD_DAYS = int(os.getenv('BUFOR_LOOKAHEAD_DAYS', 1))

VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_CLAIMS_EMAIL = os.getenv('VAPID_CLAIMS_EMAIL', 'admin@example.com')
