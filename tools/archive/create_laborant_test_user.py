#!/usr/bin/env python3
"""Create a test laborant user for testing."""

import sys
sys.path.insert(0, 'a:/GitHub/RaportProdukcyjny')

from app.core.database import get_db_connection
from werkzeug.security import generate_password_hash

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if test laborant already exists
    cursor.execute("SELECT id FROM uzytkownicy WHERE login='laborant_test'")
    if cursor.fetchone():
        print("✓ laborant_test user already exists")
    else:
        # Create test laborant user
        cursor.execute(
            "INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)",
            ('laborant_test', generate_password_hash('laborant_test123', method='pbkdf2:sha256'), 'laborant')
        )
        print("✓ Created laborant_test user with password: laborant_test123")
    
    # List all users with their roles
    cursor.execute("SELECT id, login, rola FROM uzytkownicy ORDER BY id")
    users = cursor.fetchall()
    
    print("\nAll users in system:")
    print("-" * 50)
    for row in users:
        print(f"  ID={row[0]:3d} | {row[1]:20s} | {row[2]:15s}")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\n✓ Success! You can now login with:")
    print("  Login: laborant_test")
    print("  Password: laborant_test123")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
