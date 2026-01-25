#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.abspath('.'))
from db import get_db_connection

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
    except Exception as e:
        print('Create table error:', e)
        conn.rollback()
    roles = [
        ('admin', 'Admin'),
        ('planista', 'Planista'),
        ('pracownik', 'Pracownik'),
        ('magazynier', 'Magazynier'),
        ('dur', 'DUR'),
        ('zarzad', 'Zarząd'),
        ('laboratorium', 'Laboratorium')
    ]
    try:
        for name, label in roles:
            try:
                cursor.execute("INSERT INTO roles (name, label) VALUES (%s, %s) ON DUPLICATE KEY UPDATE label=VALUES(label)", (name, label))
            except Exception:
                # fallback for DBs not supporting ON DUPLICATE
                try:
                    cursor.execute("SELECT id FROM roles WHERE name=%s", (name,))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO roles (name, label) VALUES (%s, %s)", (name, label))
                except Exception as e:
                    print('Insert role error fallback:', e)
        conn.commit()
        print('Roles table created/updated successfully.')
    except Exception as e:
        print('Insert roles error:', e)
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
