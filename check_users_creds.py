#!/usr/bin/env python3
"""Check laborant user and find test user with known credentials."""

import sys
sys.path.insert(0, 'a:/GitHub/RaportProdukcyjny')

from app.db import get_db_connection
import json

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all laborant users with first few characters of password hash
    cursor.execute("""
        SELECT id, login, rola, haslo 
        FROM uzytkownicy 
        WHERE rola = 'laborant' 
        LIMIT 10
    """)
    
    users = cursor.fetchall()
    print("Laborant Users in Database:")
    print("-" * 60)
    for row in users:
        id_val, login, rola, haslo = row
        haslo_preview = haslo[:20] if haslo else "None"
        print(f"ID={id_val:3d} | Login={login:15s} | Role={rola:10s} | Hash={haslo_preview}...")
    
    print("\n" + "="*60)
    print("Attempting to find test user (password=123)...")
    
    # Check if there's a user with a common test password
    # MD5 hash of "123" is 202cb962ac59075b964b07152d234b70
    cursor.execute("""
        SELECT id, login, rola, haslo 
        FROM uzytkownicy 
        WHERE haslo = '202cb962ac59075b964b07152d234b70' 
        OR haslo = '123'
        LIMIT 5
    """)
    
    test_users = cursor.fetchall()
    if test_users:
        print("\nFound users with common test password:")
        for row in test_users:
            print(f"  Login: {row[1]}, Role: {row[2]}")
    else:
        print("\nNo users found with common test passwords.")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
