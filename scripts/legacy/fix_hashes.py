from db import get_db_connection
from werkzeug.security import generate_password_hash

conn = get_db_connection()
cursor = conn.cursor()
admin_h = generate_password_hash('masterkey', method='pbkdf2:sha256')
plan_h = generate_password_hash('planista123', method='pbkdf2:sha256')
cursor.execute("UPDATE uzytkownicy SET haslo=%s WHERE login='admin'", (admin_h,))
cursor.execute("UPDATE uzytkownicy SET haslo=%s WHERE login='planista'", (plan_h,))
conn.commit()
print('Updated admin and planista hashes to pbkdf2:sha256')
conn.close()
