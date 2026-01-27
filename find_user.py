#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Szukaj użytkownika
cursor.execute("SELECT id, login, rola FROM uzytkownicy WHERE login LIKE '%ndzela%' OR login LIKE '%Heller%'")
users = cursor.fetchall()

if users:
    print("=== Znalezieni użytkownicy ===")
    for user_id, login, rola in users:
        print(f"ID: {user_id}, Login: {login}, Rola: {rola}")
else:
    print("Nie znaleziono użytkownika. Wyświetlam pierwsze 10:")
    cursor.execute("SELECT id, login, rola FROM uzytkownicy LIMIT 10")
    for user_id, login, rola in cursor.fetchall():
        print(f"  {login} -> {rola}")

conn.close()
