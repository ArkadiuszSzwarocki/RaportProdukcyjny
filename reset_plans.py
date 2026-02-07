#!/usr/bin/env python
"""
Reset some plans to 'zaplanowane' status for testing synchronization.
This will allow us to test the START button logic.
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

today = date.today()

# Get first 3 plans for Zasyp
cursor.execute(
    "SELECT id, produkt, status FROM plan_produkcji "
    "WHERE DATE(data_planu)=%s AND sekcja='Zasyp' "
    "ORDER BY id ASC LIMIT 3",
    (today,)
)
plans = cursor.fetchall()

print(f"Found {len(plans)} plans on Zasyp for {today}:")
for plan_id, produkt, status in plans:
    print(f"  ID {plan_id}: {produkt} (status: {status})")
    # Reset to zaplanowane
    cursor.execute(
        "UPDATE plan_produkcji SET status='zaplanowane', real_start=NULL, real_stop=NULL "
        "WHERE id=%s",
        (plan_id,)
    )

conn.commit()
print("\n✓ All plans reset to 'zaplanowane' status")
print("You can now test START button logic")

conn.close()
