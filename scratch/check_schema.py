import mysql.connector
import sys
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SHOW CREATE TABLE magazyn_opakowania")
print(cursor.fetchone()['Create Table'])
print("\n---\n")
cursor.execute("SHOW CREATE TABLE magazyn_ruch")
print(cursor.fetchone()['Create Table'])
