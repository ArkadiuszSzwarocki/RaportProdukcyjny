import mysql.connector
import socket

endpoints = [
    {"host": "raportprodukcji.mycloudnas.com", "port": 3307, "user": "biblioteka", "password": "Filipinka2025", "database": "biblioteka_testowa"},
    {"host": "192.168.0.18", "port": 3307, "user": "biblioteka", "password": "Filipinka2025", "database": "biblioteka_testowa"},
    {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "password", "database": "raportprodukcyjny"},
    {"host": "127.0.0.1", "port": 3307, "user": "biblioteka", "password": "Filipinka2025", "database": "biblioteka_testowa"},
]

print("--- Testing Socket Connection & MySQL Connect ---")
for ep in endpoints:
    host = ep["host"]
    port = ep["port"]
    print(f"\nChecking {host}:{port} ...")
    
    # 1. Test raw socket connection
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((host, port))
        print(f"  [SUCCESS] Socket connected to {host}:{port}!")
        s.close()
    except Exception as e:
        print(f"  [FAILED] Socket connect failed: {e}")
        continue
        
    # 2. Test MySQL login
    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=ep["user"],
            password=ep["password"],
            database=ep["database"],
            connection_timeout=3
        )
        print("  [SUCCESS] MySQL connected successfully!")
        conn.close()
    except Exception as e:
        print(f"  [FAILED] MySQL login failed: {e}")
