import json
import logging
from datetime import date
from flask import Flask

# Mock structure to load and init
from app.core.factory import create_app
from app.services.attendance_service import AttendanceService

app = create_app()

with app.app_context():
    try:
        res = AttendanceService.remove_from_schedule(999999)
        print("Test nonexistent ID:", res)
    except Exception as e:
        print("Error on nonexistent ID:", e)
    
    # Let's insert a dummy record and remove it
    from app.db import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # find an employee
    cursor.execute("SELECT id FROM pracownicy LIMIT 1")
    pid = cursor.fetchone()[0]
    
    cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, pracownik_id, sekcja) VALUES (%s, %s, %s)", ('2026-03-07', pid, 'Test_Sekcja'))
    conn.commit()
    inserted_id = cursor.lastrowid
    print("Inserted dummy obsada_zmiany id:", inserted_id)
    
    try:
        res2 = AttendanceService.remove_from_schedule(inserted_id)
        print("Result of removing valid id:", res2)
    except Exception as e:
        print("Error removing valid ID:", e)
    finally:
        conn.close()
