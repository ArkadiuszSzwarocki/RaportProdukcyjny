#!/usr/bin/env python
from app.db import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

current_date = date(2026, 3, 4)

# Replicate query exactly as in planning_service.py
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji
    FROM plan_produkcji
    WHERE DATE(data_planu) = %s AND status = 'zakonczone'
      AND LOWER(sekcja) = 'zasyp'
      AND (tonaz_rzeczywisty IS NULL OR tonaz_rzeczywisty < tonaz)
    ORDER BY id
""", (current_date,))

incomplete_plans = cursor.fetchall()
print(f"Found {len(incomplete_plans)} incomplete plans")

for plan in incomplete_plans:
    plan_id = plan['id']
    produkt = plan['produkt']
    plan_tonaz = plan['tonaz'] or 0
    real_tonaz = plan['tonaz_rzeczywisty'] or 0
    typ_prod = plan['typ_produkcji'] or 'worki_zgrzewane_25'
    
    remaining = plan_tonaz - real_tonaz
    
    print(f"\nPlan {plan_id}:")
    print(f"  produkt={produkt}")
    print(f"  plan_tonaz={plan_tonaz}")
    print(f"  real_tonaz={real_tonaz}")
    print(f"  remaining={remaining}")
    print(f"  typ_prod={typ_prod}")
    
    if remaining > 0:
        print(f"  → Will create Zasyp plan with plan={remaining}, real_tonaz={real_tonaz}")
        print(f"  → Will create Workowanie plan with plan={real_tonaz}, real_tonaz={real_tonaz}")
        print(f"  → Buffer will have tonaz_rzeczywisty={real_tonaz}")
    else:
        print(f"  → Skipped - remaining={remaining}")

cursor.close()
conn.close()
