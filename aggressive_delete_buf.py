import mysql.connector
from app.config import DB_CONFIG
import time

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("=== AGRESYWNE USUNIĘCIE BUF DANYCH ===\n")

try:
    # Wyłącz foreign key constraints
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    
    # 1. Delete from palety_workowanie first
    cursor.execute("""
        DELETE pw FROM palety_workowanie pw
        INNER JOIN plan_produkcji p ON pw.plan_id = p.id
        WHERE p.sekcja = 'Workowanie' AND p.nazwa_zlecenia LIKE '%_BUF%'
    """)
    pw_deleted = cursor.rowcount
    print(f"Usunięto z palety_workowanie: {pw_deleted}")
    conn.commit()
    
    # 2. Delete from plan_produkcji
    cursor.execute("""
        DELETE FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    """)
    pp_deleted = cursor.rowcount
    print(f"Usunięto z plan_produkcji: {pp_deleted}")
    conn.commit()
    
    # 3. Włącz z powrotem
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    
    # 4. Flush cache
    cursor.execute("FLUSH TABLES")
    conn.commit()
    
    time.sleep(0.5)
    
    # 5. Verify
    cursor.execute("""
        SELECT COUNT(*) FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    """)
    remaining = cursor.fetchone()[0]
    
    print(f"\nPo usunięciu - pozostało: {remaining}")
    
    if remaining == 0:
        print("✅ WSZYSTKIE BUF DANE USUNIĘTE!")
    else:
        print(f"❌ NADAL {remaining} WIERSZY!")
        # List remaining
        cursor.execute("""
            SELECT id, produkt, nazwa_zlecenia FROM plan_produkcji 
            WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
            LIMIT 5
        """)
        for row in cursor.fetchall():
            print(f"  - Still exists: ID {row[0]} | {row[1]} | {row[2]}")
        
except Exception as e:
    print(f"❌ BŁĄD: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()
