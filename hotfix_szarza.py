"""HOTFIX: Add missing szarża for Zasyp plans and ensure Workowanie plans exist"""

from app.db import get_db_connection
from datetime import datetime

conn = get_db_connection()
cursor = conn.cursor()

try:
    # Find Zasyp plans without szarża
    cursor.execute("""
        SELECT id, produkt, tonaz, typ_produkcji
        FROM plan_produkcji p
        WHERE DATE(data_planu) = CURDATE()
        AND sekcja = 'Zasyp'
        AND is_deleted = 0
        AND NOT EXISTS (
            SELECT 1 FROM szarze s
            INNER JOIN plan_produkcji pr ON s.plan_id = pr.id
            WHERE s.plan_id = p.id
            AND DATE(s.data_dodania) = DATE(p.data_planu)
        )
        ORDER BY p.id
    """)
    
    missing_szarze = cursor.fetchall()
    print(f"Found {len(missing_szarze)} Zasyp plans without szarża")
    
    for plan in missing_szarze:
        plan_id, produkt, tonaz, typ = plan
        print(f"\n  Fixing: Plan ID {plan_id} ({produkt})")
        
        # Add szarża
        now = datetime.now()
        godzina = now.strftime('%H:%M:%S')
        
        cursor.execute(
            "INSERT INTO szarze (plan_id, waga, data_dodania, godzina, pracownik_id, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (plan_id, tonaz, now, godzina, None, 'zarejestowana')
        )
        
        cursor.execute(
            "UPDATE plan_produkcji SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id=%s",
            (tonaz, plan_id)
        )
        
        # Ensure Workowanie plan exists
        cursor.execute(
            "SELECT id FROM plan_produkcji WHERE data_planu=CURDATE() AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s",
            (produkt, typ or '')
        )
        workowanie = cursor.fetchone()
        
        if not workowanie:
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=CURDATE() AND sekcja='Workowanie'")
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1
            
            cursor.execute(
                "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (datetime.now().date(), produkt, 0, 'zaplanowane', 'Workowanie', nk, typ or '', 0)
            )
            print(f"    Created new Workowanie plan")
        else:
            cursor.execute(
                "UPDATE plan_produkcji SET status='zaplanowane', real_start=NULL, real_stop=NULL WHERE id=%s",
                (workowanie[0],)
            )
            print(f"    Reset existing Workowanie plan ID {workowanie[0]}")
        
        print(f"    ✅ Added szarża for plan {plan_id}")
    
    # Remove duplicate Workowanie plans (ones without corresponding szarża)
    print("\n\nCleaning up duplicate Workowanie plans without szarża...")
    cursor.execute("""
        SELECT p.id, p.produkt
        FROM plan_produkcji p
        WHERE DATE(p.data_planu) = CURDATE()
        AND p.sekcja = 'Workowanie'
        AND p.is_deleted = 0
        AND NOT EXISTS (
            SELECT 1 FROM szarze s
            INNER JOIN plan_produkcji pr ON s.plan_id = pr.id
            WHERE s.status = 'zarejestowana'
            AND DATE(s.data_dodania) = DATE(p.data_planu)
            AND pr.produkt = p.produkt
        )
        ORDER BY p.id
    """)
    
    orphaned = cursor.fetchall()
    for plan_id, produkt in orphaned:
        cursor.execute("UPDATE plan_produkcji SET is_deleted = 1 WHERE id = %s", (plan_id,))
        print(f"  ✅ Soft-deleted orphaned Workowanie plan ID {plan_id} ({produkt})")
    
    conn.commit()
    print("\n✅ HOTFIX COMPLETE - Database fixed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()
