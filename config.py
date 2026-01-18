import os
from dotenv import load_dotenv

# Wczytaj zmienne z pliku .env
load_dotenv()

# Klucz do sesji (pobierany z .env, a jeśli brak - używa domyślnego)
SECRET_KEY = os.getenv('SECRET_KEY', 'tajnyKluczAgronetzwerk')

# Dane do bazy - teraz pobierane bezpiecznie z .env
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'user': os.getenv('DB_USER', 'biblioteka'),
    'password': os.getenv('DB_PASSWORD', ''),  # Puste domyślnie, wymusza pobranie z .env
    'charset': 'utf8mb4'
}

# Folder raportów
if not os.path.exists('raporty'):
    os.makedirs('raporty')