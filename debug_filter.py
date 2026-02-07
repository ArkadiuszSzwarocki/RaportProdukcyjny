from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Test QueryHelper filter for Workowanie - WITH EXISTS
cursor.execute("""
    SELECT id, produkt, tonaz, status, real_start, real_stop, 
    TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, kolejnosc, 
    typ_produkcji, wyjasnienie_rozbieznosci 
    FROM plan_produkcji p 
    WHERE DATE(p.data_planu) = CURDATE() AND LOWER(p.sekcja) = LOWER('Workowanie') AND p.status != 'nieoplacone' AND p.is_deleted = 0 
      AND EXISTS ( 
        SELECT 1 FROM szarze s 
        INNER JOIN plan_produkcji pr ON s.plan_id = pr.id 
        WHERE s.status = 'zarejestowana' 
          AND DATE(s.data_dodania) = DATE(p.data_planu) 
          AND pr.produkt = p.produkt 
      ) 
    ORDER BY CASE p.status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, 
    p.kolejnosc ASC, p.id ASC
""")

plans_with_filter = cursor.fetchall()
print(f"=== WORKOWANIE WITH EXISTS FILTER ===")
print(f"Total plans: {len(plans_with_filter)}")
for p in plans_with_filter:
    print(f"  ID {p[0]}: {p[1]} | status={p[3]} | tonaz={p[2]} | rzeczywisty={p[7]}")

# Test WITHOUT EXISTS (just all Workowanie plans)
print()
cursor.execute("""
    SELECT id, produkt, tonaz, status, tonaz_rzeczywisty
    FROM plan_produkcji 
    WHERE DATE(data_planu) = CURDATE() 
    AND sekcja = 'Workowanie'
    AND is_deleted = 0
""")

plans_all = cursor.fetchall()
print(f"=== ALL WORKOWANIE (NO FILTER) ===")
print(f"Total plans: {len(plans_all)}")
for p in plans_all:
    print(f"  ID {p[0]}: {p[1]} | status={p[3]} | tonaz={p[2]} | rzeczywi={p[4]}")

# Check szarża count
print()
cursor.execute("""
    SELECT COUNT(*), COUNT(DISTINCT produkt) 
    FROM szarze 
    WHERE DATE(data_dodania) = CURDATE()
""")
szarze_count = cursor.fetchone()
print(f"=== SZARŻA TODAY ===")
print(f"Total szarża records: {szarze_count[0]}")
print(f"Distinct products: {szarze_count[1]}")

cursor.close()
conn.close()
