import mysql.connector
from app.config import DB_CONFIG

# Direct connection without ORM/wrapper
conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

try:
    print("=== USUWANIE WSZYSTKICH BUF WIERSZY ===\n")
    
    # 1. Delete Workowanie with _BUF
    cursor.execute("""
        DELETE FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    """)
    work_deleted = cursor.rowcount
    print(f"Usunięto Workowanie: {work_deleted}")
    conn.commit()
    
    # 2. Verify
    cursor.execute("""
        SELECT COUNT(*) FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    """)
    remaining = cursor.fetchone()[0]
    print(f"Pozostało Workowanie BUF: {remaining}")
    
    if remaining == 0:
        print("\n✅ WSZYSTKO USUNIĘTE!")
    else:
        print(f"\n❌ NADAL {remaining} WIERSZY!")
        
except Exception as e:
    print(f"❌ BŁĄD: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()
