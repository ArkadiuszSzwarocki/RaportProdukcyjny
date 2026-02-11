import subprocess
import os

# Get DB config from .env  
from app.config import DB_CONFIG

host = DB_CONFIG.get('host', 'localhost')
port = DB_CONFIG.get('port', 3307)
user = DB_CONFIG.get('user', 'biblioteka')
password = DB_CONFIG.get('password', '')
db = DB_CONFIG.get('database', 'biblioteka')

# SQL commands
sql_delete = "DELETE FROM plan_produkcji WHERE sekcja='Workowanie' AND nazwa_zlecenia LIKE '%_BUF%';"
sql_verify = "SELECT COUNT(*) as remaining FROM plan_produkcji WHERE sekcja='Workowanie' AND nazwa_zlecenia LIKE '%_BUF%';"

# Run mysql command
cmd = [
    'mysql',
    '-h', host,
    '-P', str(port),
    '-u', user,
    f'-p{password}',
    '-D', db,
    '-e', sql_delete + sql_verify
]

print("Uruchamiam MySQL CLI...")
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
