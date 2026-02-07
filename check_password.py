from app.db import get_db_connection
from werkzeug.security import check_password_hash

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("SELECT id, login, haslo FROM uzytkownicy WHERE login='admin'")
admin = cursor.fetchone()

if admin:
    admin_id, login, hashed = admin
    print(f"Admin account:")
    print(f"  Login: {login}")
    print(f"  Password hash: {hashed[:50] if hashed else 'NULL'}...")
    print(f"  Hash format: {'bcrypt' if hashed and hashed.startswith('$2') else ('md5' if hashed and len(hashed) == 32 else ('sha' if hashed and len(hashed) == 40 else 'plaintext or other'))}")
    
    # Test if it's plaintext or hashed
    if hashed and hashed.startswith(('$2', 'pbkdf2:', 'sha256:')):
        print("  ✓ Password appears to be hashed")
        # Try to verify password
        if check_password_hash(hashed, 'admin123'):
            print("  ✓ Password 'admin123' matches!")
        else:
            print("  ✗ Password 'admin123' does NOT match")
    else:
        print("  ✗ Password might be plaintext!")
        if hashed == 'admin123':
            print("    (and equals 'admin123')")

conn.close()
