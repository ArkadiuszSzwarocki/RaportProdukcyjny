import os
from dotenv import load_dotenv

# Wczytaj zmienne z pliku .env, ale nie nadpisuj wartości już ustawionych
# w środowisku (np. w CI).
load_dotenv(override=False)

# Klucz do sesji (pobierany z .env, a jeśli brak - używa domyślnego)
SECRET_KEY = os.getenv('SECRET_KEY', 'tajnyKluczAgronetzwerk')

# Dane do bazy - teraz pobierane bezpiecznie z .env
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'user': os.getenv('DB_USER', 'biblioteka'),
    'password': os.getenv('DB_PASSWORD', ''),  # Puste domyślnie, wymusza pobranie z .env
    'charset': 'utf8mb4',
    'connection_timeout': 5,  # 5 sekund timeout
    'autocommit': False
}

# Konfiguracja odbiorców raportów email
# Listę możesz przesłonić zmienną środowiskową EMAIL_RECIPIENTS (oddzieleni przecinkami)
EMAIL_RECIPIENTS = os.getenv('EMAIL_RECIPIENTS', 'lider@example.com,szef@example.com,biuro@example.com').split(',')
EMAIL_RECIPIENTS = [email.strip() for email in EMAIL_RECIPIENTS if email.strip()]  # Czyść i filtruj

# ================= FLASK-MAIL CONFIGURATION =================
# Konfiguracja wysyłania maili z serwera (ze załącznikami raportów)
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False') == 'True'
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')  # Np. noreply@firma.pl
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')  # App password
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'Raport Produkcyjny <noreply@firma.pl>')

# ================ FOLDER CONFIGURATION =================
# Folder raportów
if not os.path.exists('raporty'):
    os.makedirs('raporty')

# Session timeout (minutes) - use env var to override. Default: 40 minutes
SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', 720))

# Bufor - zakres dat (ile dni wstecz i do przodu uwzględniać przy odświeżaniu bufora)
# Domyślnie: 1 dzień wstecz i 1 dzień do przodu (stałe, można nadpisać w .env)
BUFOR_LOOKBACK_DAYS = int(os.getenv('BUFOR_LOOKBACK_DAYS', 1))
BUFOR_LOOKAHEAD_DAYS = int(os.getenv('BUFOR_LOOKAHEAD_DAYS', 1))

# ================ WEB PUSH (VAPID) CONFIGURATION =================
# Generuj klucze raz: scratch/gen_vapid.py
# Klucze przechowywane w .env jako VAPID_PRIVATE_KEY i VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_CLAIMS_EMAIL = os.getenv('VAPID_CLAIMS_EMAIL', 'admin@agronetzwerk.pl')
