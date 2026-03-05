#!/usr/bin/env python
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Check plan 1350
cursor.execute("SELECT id, sekcja, produkt, plan, tonaz_rzeczywisty, data_planu FROM plan_produkcji WHERE id=1350")
plan_1350 = cursor.fetchone()
print("Plan 1350 (Zasyp):", plan_1350)

# Check original plan 1262 that was the source
cursor.execute("SELECT id, sekcja, produkt, plan, tonaz_rzeczywisty, data_planu FROM plan_produkcji WHERE id=1262")
plan_1262 = cursor.fetchone()
print("Plan 1262 (original Zasyp):", plan_1262)

cursor.close()
conn.close()
