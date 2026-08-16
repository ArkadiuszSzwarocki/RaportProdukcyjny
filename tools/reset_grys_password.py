import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection
from werkzeug.security import generate_password_hash

sys.stdout.reconfigure(encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor()

# Set password of GrysDawi to 'haslo123'
new_hash = generate_password_hash('haslo123')
cursor.execute("UPDATE uzytkownicy SET haslo = %s WHERE login = 'GrysDawi'", (new_hash,))
conn.commit()

print("GrysDawi password successfully updated in database!")
conn.close()
