from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

try:
    # Get IDs first
    cursor.execute("""
        SELECT id FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    """)
    
    plan_ids = [row[0] for row in cursor.fetchall()]
    print(f"Znaleziono {len(plan_ids)} zleceń BUF do usunięcia")
    
    if plan_ids:
        # Delete with individual IDs
        for plan_id in plan_ids:
            print(f"Usuwam ID {plan_id}...")
            cursor.execute("DELETE FROM palety_workowanie WHERE plan_id = %s", (plan_id,))
            cursor.execute("DELETE FROM plan_produkcji WHERE id = %s", (plan_id,))
            conn.commit()
            print(f"  ✓ Usunięto ID {plan_id}")
        
        # Verify
        cursor.execute("""
            SELECT COUNT(*) FROM plan_produkcji 
            WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
        """)
        remaining = cursor.fetchone()[0]
        print(f"\n✅ Pozostało: {remaining} BUF zleceń")
        
except Exception as e:
    print(f"❌ BŁĄD: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()
