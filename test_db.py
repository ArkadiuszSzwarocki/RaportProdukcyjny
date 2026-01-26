#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test skryptu połączenia z bazą danych
Uruchom ten skrypt aby sprawdzić czy połączenie z MySQL działa poprawnie
"""

import mysql.connector
from mysql.connector import Error
import pytest
import os
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych z pliku .env
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Maskowanie wrażliwych danych
def masked(v):
    if not v: return None
    return v[:3] + '...' + v[-3:] if len(v) > 6 else '***'

# Powszechnie używane nazwy zmiennych
DATABASE_URL = os.getenv('DATABASE_URL')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT') or os.getenv('PORT')
DB_USER = os.getenv('DB_USER') or os.getenv('MYSQL_USER') or os.getenv('USER')
DB_PASS = os.getenv('DB_PASS') or os.getenv('MYSQL_PASSWORD') or os.getenv('PASSWORD')
DB_NAME = os.getenv('DB_NAME') or os.getenv('MYSQL_DB') or os.getenv('DATABASE')

print("Wykryte zmienne środowiskowe:")
print(" DATABASE_URL:", bool(DATABASE_URL))
print(" DB_HOST:", masked(DB_HOST))
print(" DB_PORT:", DB_PORT)
print(" DB_USER:", masked(DB_USER))
print(" DB_NAME:", masked(DB_NAME))

# Najpierw próbuj połączenia przez DATABASE_URL (SQLAlchemy), w przeciwnym razie przez pymysql
if DATABASE_URL:
    try:
        from sqlalchemy import create_engine, text
        eng = create_engine(DATABASE_URL, connect_args={})
        with eng.connect() as conn:
            r = conn.execute(text("SELECT 1")).scalar()
        print("Połączenie przez DATABASE_URL: OK, SELECT 1 ->", r)
        raise SystemExit(0)
    except Exception as e:
        print("Błąd połączenia przez DATABASE_URL:", e)

if DB_HOST and DB_USER and DB_PASS and DB_NAME:
    try:
        import pymysql
        port = int(DB_PORT) if DB_PORT else 3306
        conn = pymysql.connect(host=DB_HOST, port=port, user=DB_USER, password=DB_PASS, database=DB_NAME, connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            r = cur.fetchone()
        conn.close()
        print("Połączenie przez pymysql: OK, SELECT 1 ->", r)
        raise SystemExit(0)
    except Exception as e:
        print("Błąd połączenia przez pymysql:", e)

print("Nie udało się połączyć — sprawdź nazwy zmiennych w .env i czy wymagane pakiety są zainstalowane.")
