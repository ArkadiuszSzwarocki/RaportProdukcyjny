import socket
from app.db import get_db_connection

def test_tcp(ip, port=9100, timeout=2):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True, "OK"
    except Exception as e:
        return False, str(e)

def main():
    conn = get_db_connection()
    try:
        # Check if cursor supports dictionary-like access
        with conn.cursor() as cursor:
            # 1. Fetch all active printers
            cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna=1 ORDER BY id")
            printers = cursor.fetchall()
            
            # 2. Emulate selection logic
            cursor.execute("""
                SELECT id, nazwa, ip, lokalizacja
                FROM drukarki
                WHERE aktywna = 1
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                        WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                        ELSE 2
                    END,
                    id ASC
                LIMIT 1
            """)
            preferred = cursor.fetchone()

            # Detect if results are dicts or tuples
            is_dict = isinstance(printers[0], dict) if printers else False
            
            def get_val(row, key, index):
                return row[key] if is_dict else row[index]

            preferred_id = get_val(preferred, "id", 0) if preferred else None

            print(f"{'ID':<4} | {'Nazwa':<25} | {'IP':<15} | {'TCP OK':<8} | {'Blad':<20} | {'Status'}")
            print("-" * 100)
            
            for p in printers:
                pid = get_val(p, "id", 0)
                pname = get_val(p, "nazwa", 1)
                pip = get_val(p, "ip", 2)
                
                ok, err = test_tcp(pip)
                status = "[PREFERRED]" if pid == preferred_id else ""
                tcp_status = "YES" if ok else "NO"
                print(f"{pid:<4} | {pname:<25} | {pip:<15} | {tcp_status:<8} | {err[:20]:<20} | {status}")
                
            if preferred:
                pname = get_val(preferred, "nazwa", 1)
                pip = get_val(preferred, "ip", 2)
                print(f"\nWybrana drukarka (preferowana): {pname} ({pip})")
            else:
                print("\nNie znaleziono zadnej aktywnej drukarki.")
                
    finally:
        conn.close()

if __name__ == '__main__':
    main()
