#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.abspath('.'))
from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL UNIQUE,
            label VARCHAR(100) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
        conn.commit()
        cursor.execute("INSERT INTO roles (name,label) VALUES (%s,%s) ON DUPLICATE KEY UPDATE label=VALUES(label)", ('laborant','Laborant'))
        conn.commit()
        print('Role "laborant" inserted/updated successfully.')
    except Exception as e:
        print('Error inserting role:', e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()
