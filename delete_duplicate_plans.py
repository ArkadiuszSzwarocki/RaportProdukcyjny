#!/usr/bin/env python3
"""Delete duplicate plan ID 915 and its related Zasyp 914"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("🗑️ Usuwanie duplikatów...")
print()

# Usuń Workowanie ID 915
cursor.execute("DELETE FROM plan_produkcji WHERE id = 915")
deleted_work = cursor.rowcount
print(f"✅ Usunięto Workowanie ID 915: {deleted_work} wierszy")

# Usuń Zasyp ID 914
cursor.execute("DELETE FROM plan_produkcji WHERE id = 914")
deleted_zasyp = cursor.rowcount
print(f"✅ Usunięto Zasyp ID 914: {deleted_zasyp} wierszy")

# Usuń szarże powiązane z Zasyp 914
cursor.execute("DELETE FROM szarze WHERE plan_id = 914")
deleted_szarze = cursor.rowcount
print(f"✅ Usunięto szarże dla Zasyp 914: {deleted_szarze} wierszy")

# Usuń bufory powiązane z Zasyp 914
cursor.execute("DELETE FROM bufor WHERE zasyp_id = 914")
deleted_bufor = cursor.rowcount
print(f"✅ Usunięto bufory dla Zasyp 914: {deleted_bufor} wierszy")

conn.commit()
print()
print("✅ Wszystkie duplikaty usunięte!")

conn.close()
