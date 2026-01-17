# Biblioteka - Konfiguracja

## Konfiguracja Bazy Danych

### 1. Utwórz bazę danych MySQL

Zaloguj się do MySQL i wykonaj:

```sql
CREATE DATABASE biblioteka CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'biblioteka'@'localhost' IDENTIFIED BY 'twoje_haslo';
GRANT ALL PRIVILEGES ON biblioteka.* TO 'biblioteka'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Skonfiguruj połączenie w app.py

Otwórz plik `app.py` i zmień parametry w sekcji `db_config` (linie 11-18):

```python
db_config = {
    'host': 'localhost',           # lub adres IP serwera MySQL
    'port': 3307,                  # standardowy port MySQL
    'database': 'biblioteka',      # nazwa bazy danych
    'user': 'biblioteka',          # użytkownik bazy
    'password': 'twoje_haslo',     # hasło użytkownika
    'charset': 'utf8mb4'
}
```

### 3. Zmień klucz sesji (WAŻNE!)

W pliku `app.py` linia 8:

```python
app.secret_key = 'wygeneruj-losowy-długi-ciąg-znaków-tutaj'
```

Możesz wygenerować bezpieczny klucz w Pythonie:

```python
import secrets
print(secrets.token_hex(32))
```

## Konfiguracja dla środowiska produkcyjnego

### 1. Wyłącz tryb debugowania

W pliku `app.py` ostatnia linia:

```python
app.run(debug=False, host='0.0.0.0', port=5000)
```

### 2. Użyj serwera WSGI

Zamiast wbudowanego serwera Flask, użyj Gunicorn (Linux) lub Waitress (Windows):

**Linux/Mac:**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

**Windows:**
```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### 3. Skonfiguruj HTTPS (Rekomendowane)

Użyj reverse proxy jak Nginx lub Apache z certyfikatem SSL.

### 4. Zmień domyślne hasła

Po pierwszym uruchomieniu:
1. Zaloguj się jako admin (admin / masterkey)
2. Przejdź do panelu admina
3. Zmień hasła dla wszystkich domyślnych kont

## Backup bazy danych

### Tworzenie kopii zapasowej

```bash
mysqldump -u biblioteka -p biblioteka > backup_$(date +%Y%m%d).sql
```

### Przywracanie z kopii

```bash
mysql -u biblioteka -p biblioteka < backup_20260117.sql
```

## Zmienne środowiskowe (Opcjonalnie)

Możesz przenieść konfigurację do zmiennych środowiskowych:

**Windows:**
```cmd
set DB_HOST=localhost
set DB_PORT=3307
set DB_NAME=biblioteka
set DB_USER=biblioteka
set DB_PASSWORD=haslo
set SECRET_KEY=twoj-tajny-klucz
```

**Linux/Mac:**
```bash
export DB_HOST=localhost
export DB_PORT=3307
export DB_NAME=biblioteka
export DB_USER=biblioteka
export DB_PASSWORD=haslo
export SECRET_KEY=twoj-tajny-klucz
```

Następnie w `app.py`:

```python
import os

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'user': os.getenv('DB_USER', 'biblioteka'),
    'password': os.getenv('DB_PASSWORD', ''),
    'charset': 'utf8mb4'
}

app.secret_key = os.getenv('SECRET_KEY', 'zmien-to-natychmiast')
```

## Testowanie połączenia

Utwórz plik `test_db.py`:

```python
import mysql.connector

db_config = {
    'host': 'localhost',
    'port': 3307,
    'database': 'biblioteka',
    'user': 'biblioteka',
    'password': 'twoje_haslo',
    'charset': 'utf8mb4'
}

try:
    conn = mysql.connector.connect(**db_config)
    print("✅ Połączenie z bazą danych OK!")
    conn.close()
except Exception as e:
    print(f"❌ Błąd połączenia: {e}")
```

Uruchom: `python test_db.py`

## Porty i Firewall

Upewnij się, że następujące porty są otwarte:

- **5000** - Aplikacja Flask (domyślnie)
- **3307/3307** - MySQL Server

## Logowanie

Aby włączyć logowanie do pliku, dodaj na początku `app.py`:

```python
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler('app.log', maxBytes=10000000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)
```
