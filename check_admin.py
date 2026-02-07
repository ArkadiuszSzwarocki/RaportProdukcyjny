#!/usr/bin/env python
"""Check admin user in database"""
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check if admin table exists
cursor.execute("SELECT * FROM pracownicy WHERE login='admin' LIMIT 1")
admin = cursor.fetchone()

if admin:
    print(f"✓ Admin exists:")
    print(f"  ID: {admin[0]}")
    print(f"  Login: {admin[1]}")
    print(f"  Role: {admin[3] if len(admin) > 3 else 'unknown'}")
    print(f"  Password hash exists: {bool(admin[2])}")
else:
    print("✗ Admin user NOT found in database!")
    
    # Try to create default admin
    print("\n[INFO] Creating default admin user...")
    import os
    admin_pass = os.getenv('INITIAL_ADMIN_PASSWORD', 'admin123')
    from werkzeug.security import generate_password_hash
    
    hashed = generate_password_hash(admin_pass)
    try:
        cursor.execute(
            "INSERT INTO pracownicy (login, haslo_hash, rola) VALUES (%s, %s, %s)",
            ('admin', hashed, 'admin')
        )
        conn.commit()
        print(f"✓ Created admin with password: {admin_pass}")
    except Exception as e:
        print(f"✗ Error creating admin: {e}")

# List all users
print("\nAll users in database:")
cursor.execute("SELECT login, rola FROM pracownicy ORDER BY login")
users = cursor.fetchall()
for login, rola in users:
    print(f"  - {login:20s} ({rola})")

conn.close()
