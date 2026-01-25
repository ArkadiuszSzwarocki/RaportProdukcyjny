#!/usr/bin/env python
"""Test pobierania raportów z bazy"""
import json
from datetime import date
from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Pobierz ostatni raport
dzisiaj = date.today()
cursor.execute("""
    SELECT id, summary_json, sekcja FROM raporty_koncowe 
    WHERE data_raportu = %s 
    ORDER BY id DESC 
    LIMIT 1
""", (dzisiaj,))

result = cursor.fetchone()
if result:
    print("ID:", result[0])
    print("SEKCJA:", result[2])
    print("\nJSON:")
    data = json.loads(result[1])
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print("Brak raportu dla", dzisiaj)

conn.close()
